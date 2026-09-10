---
title: "Cockpit 3D HMI Localization: A Tool for Importing Translation Tables"
date: 2026-06-09
series: localization
no: 
status: published
visibility: public
wechat_url: ""
lang: en
---

> The previous article covered how to obtain Locales. Before we actually get into the concrete work of localization, there is one thing we're still missing—the translation table. In previous projects, the product team led the collaboration on translation work: each application's developers consolidated the items to be translated into spreadsheet files, and the product team consolidated all modules to be translated plus project-level change information. Storage, release, translation, and change management of the copy were all done through the Weblate platform. Developers downloaded the translation tables for their vehicle-model project and application from Weblate.

Once we have such a CSV file, or several, we need to import it into our editor so it exists as an asset accessible at runtime.

---

## 1. The CSV Import Tool

### 1.1 What the Files Look Like

What the translation platform delivers for a single app is, after export, a folder:

- Inside the folder, files are named by language, such as `zh_Hans.csv`, `en.csv`, `nb_NO.csv`, `he_IL.csv`, and so on
- Each file has two columns: `id` (the unique identifier of a translation entry) and `target` (the translated text in that language)
- The Simplified Chinese file is mandatory (it is the alignment baseline for all languages under this tool's workflow)

For example:

```
id,target
card_full_title,车况
hvac_temp_unit,温度单位
```

### 1.2 Two Roles

- **CSVUtility**: a pure data layer with no engine dependency, responsible for generic CSV file reading and writing. It defines two generic interfaces, `ICSVReader` / `ICSVWriter`; any editor tool that needs to read or write CSV can reuse it.
- **LocalizationTool**: the editor's operational panel layer, responsible for writing CSV data into, for example, Unity Localization's `StringTableCollection`. It relies on `CSVUtility` for file parsing, while it itself handles how the parsed data is converted into engine assets.

So `CSVUtility` is the abstraction of "how to read," and `LocalizationTool` is the concrete logic of "how to write."

![图1](./图1.png)

`ICSVReader`: the first line of the CSV is parsed into a dictionary `Dictionary<string, 列号>` (columns starting with `#` are skipped), then each subsequent row instantiates a generic object; calling `Reader(headers, values)` lets the object pull its values from the string array by column name. A CSV of any structure can be parsed as long as you implement one `Reader` method.

```csharp
// The following is illustrative code.
public class SourceCSVItem : ICSVReader
{
    public string id;
    public string target;

    public void Reader(Dictionary<string, int> headers, string[] values)
    {
        id = values[headers["id"]];
        target = values[headers["target"]];
    }
}
```

`ICSVWriter`: suitable for use after a CSV file has been read, when you need to output a data-change log.

### 1.3 The Import Flow

`LocalizationTool` is an `EditorWindow` whose menu path you can define yourself.

How to use it: drag the folder containing the CSVs into the window and click "Import."

**Import approach**: In my earlier Unity work, the `Import` function doesn't scan the folder for CSVs. Instead it iterates over the `StringTable`s already registered in the `StringTableCollection`, building `{code}.csv` paths from `LocaleIdentifier.Code` to read them. If a language's CSV file is missing, `CSVUtility.Reader` throws an exception.

The flow has six steps:


| Step  | Method                   | What it does                                   |
| --- | -------------------- | ------------------------------------- |
| 1   | `CleanData`          | Removes empty rows in the CSV where `target == "\"\""`     |
| 2   | `CreateTargetDic`    | Uses the Simplified Chinese table as the key source and builds an `{id → TargetCSVItem}` dictionary |
| 3   | `FillData`           | Fills other languages' CSV data into the corresponding `TargetCSVItem` fields |
| 4   | `Check`              | Compares existing entries against the new CSV's Simplified Chinese set (Warning only)     |
| 5   | `UpdateLocalization` | Incrementally writes into the StringTable                      |
| 6   | `ExportLog`          | Exports the change log as a CSV file on the desktop                   |


Core design: **the Simplified Chinese table is the master table**.

During file processing, `CreateTargetDic` builds the dictionary from all id values in zh_Hans.csv, and in `FillData`, if an id exists in another language's table but not in the Simplified Chinese table, it throws an exception immediately. This step guarantees the input data is aligned first.

However, when writing into the engine's Localization StringTable, alignment is by the **Chinese text**. That way, when a UI component initializes, it can directly use the Chinese text it is currently displaying as the key to look up the table—no configuration of any kind needed. This effectively eliminates the workload of "assigning keys."

```csharp
// The following is illustrative code
private void Import()
{
    var collection = LocalizationEditorSettings.GetStringTableCollection("LanguageTable");
    var sourceData = new Dictionary<LocaleIdentifier, List<SourceCSVItem>>();

    // Iterate over the registered StringTables, build CSV paths per Locale, and read them
    foreach (var stringTable in collection.StringTables)
    {
        string code = stringTable.LocaleIdentifier.Code;
        code = AdaptFileName(code); // underscore/hyphen mapping
        string csvPath = $"{droppedFolderPath}/{code}.csv";
        sourceData[stringTable.LocaleIdentifier] = CSVUtility.Reader<SourceCSVItem>(csvPath);
    }

    var targetData = CreateTargetDic(sourceData, zhLocale);  // Simplified Chinese as the key
    FillData(sourceData, targetData);                         // fill in the other languages
    Check(targetData, (StringTable)collection.GetTable(zhLocale));
    UpdateLocalization(targetData, collection, zhLocale, logs);
    ExportLog(logs);

    // Mark dirty and save
    collection.StringTables.ForEach(t => EditorUtility.SetDirty(t));
    AssetDatabase.SaveAssets();
}
```

---

## 2. Entering the Table Data

### 2.1 From CSV to Unity

The Unity Localization Package is designed as a three-layer structure:


| Layer       | Class                                          | Responsibility                                                              | Usage in this project                                                                                 |
| -------- | ------------------------------------------ | --------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| **Configuration layer**  | `LocalizationSettings`                     | Manages the list of available Locales, the currently selected Locale, and the Startup Behavior                     | Stored as `Localization Settings.asset`, with 15 Locales registered                                     |
| **Data layer**  | `StringTableCollection` → `StringTable`    | Each Locale gets one `StringTable`, internally a `{key → StringTableEntry}` dictionary | The collection is named `"LanguageTable"`, with 15 tables such as `LanguageTable_zh-Hans.asset`, `LanguageTable_en.asset` |
| **Runtime layer** | `LocalizedString` / `LocalizedStringTable` | Holds references to tables and entries; automatically fetches the latest translation when the Locale switches                                   | `LocalizationText` fetches values via `Keys[i].GetLocalizedString()`                                |


The API chain `LocalizationTool` operates when writing:

1. **Get the collection**: `LocalizationEditorSettings.GetStringTableCollection("LanguageTable")` — retrieves the collection containing 15 `StringTable`s
2. **Iterate the tables**: each entry in `collection.StringTables` corresponds to one Locale
3. **Look up entries**: `stringTable.GetEntry(key)` checks whether the key already exists
4. **Write entries**: `stringTable.AddEntry(key, value)` adds or overwrites one record
5. **Persist**: `EditorUtility.SetDirty` + `AssetDatabase.SaveAssets()` marks the assets dirty and saves them

```csharp
// The following is illustrative code
foreach (var item in targetData)
{
    foreach (var stringTable in collection.StringTables)
    {
        var key = item.Value.Get(zhLocale);  // the Simplified Chinese text serves as the StringTable key
        var value = item.Value.Get(stringTable.LocaleIdentifier);
        var entry = stringTable.GetEntry(key);

        if (entry == null)
            stringTable.AddEntry(key, value);  // add
        else if (entry.Value != value)
            stringTable.AddEntry(key, value);  // update (overwrite)
        // entry exists and value matches → skip
    }
}
```

At runtime, `LocalizationText` fetches translations from the current Locale's `StringTable` via `Keys[i].GetLocalizedString()`. For Arabic and Hebrew, `LocalizationText` must additionally perform RTL glyph reordering—that part deserves its own article.

Here, the StringTable key is the Simplified Chinese text itself, not the `id` field from the translation platform. The benefit of using Chinese as the key was mentioned above: because the UI component's initialized value is the Chinese text rather than the id, this saves work. But if your multilingual-reactive UI design has the concept of an id, then using Chinese is unnecessary. In my case, the id style was inconsistent—some were numeric codes, some pure English. That was a legacy problem caused by having no constraints when the translation requirements were first entered.

### 2.2 From CSV to Unreal

Unreal's Localization Dashboard has built-in import/export of copy: you can export all `FText` strings to `.csv`, have them translated, and re-import—a complete engine-native workflow. But its prerequisite is that the text already exists in scripts or Blueprints. So you have to Gather first, then Export, then Import after translation.

But when you already have a translation team with a delivery platform and need to **import translations directly from external CSVs**, you should look at DataTable, the generic structured-data import mechanism: Unreal's `UDataTable` natively supports importing structured data from CSV/JSON, the engine automatically parses it into rows based on `FTableRowBase`, and lookups at runtime go through `FDataTableRowHandle`. Unreal has both the import and the runtime lookup built in.

---

## Closing

From this point on, the data has flowed from spreadsheet files into the development tools, existing as an asset. However, table import as a need goes far beyond translation: vehicle-part configuration, UI configuration, and signal configuration can all be driven by tables too. That said, if you merely convert xlsx files into json files and drop them into the engine, I actually think that's a bit roundabout given the development complexity of this industry. If you're going to build data-table-based management, turning desktop files into engine assets is the more meaningful approach.
