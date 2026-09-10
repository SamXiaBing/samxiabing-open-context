---
title: "3D HMI Fidelity: Camera Motion Curves — From Formula to Asset"
lang: en
date: 2026-05-19
series: misc
no: 
status: published
visibility: public
wechat_url: ""
---

> The previous article described the idea of using Adobe After Effects camera parameters as the design foundation for the camera animation module. As mentioned there, every camera animation parameter can have its start and end points configured, along with the animation duration and the easing curve.
>
> As for the curves, I assumed the handful of options in the DOTween plugin would surely be enough. Only later did I realize that my own sensitivity to motion rhythm simply wasn't refined enough.

---

## 1. Where this came from

In camera animation, the motion rhythm is controlled by an AnimationCurve. In Unity, we can easily get all the classic curves: Linear, EaseIn, EaseOut, EaseInOut, and so on.

In our project, HMI motion design often calls for a "fast start, slow settle" rhythm for camera movement. Even when we used a curve like easeOutExpo — already heavily biased toward "fast then slow" — the motion designers still felt the moment the camera finally stopped wasn't right: the opening wasn't fast enough, and the easing right before the freeze lacked grace. And the whole sequence lasts only 1000ms (800–1200).

At that point, the artists pull out a formula and demand the motion be reproduced according to it. Hunting for a matching preset curve in the project is time-consuming and may turn up nothing — which is why I wanted a tool that takes a formula as input and outputs a curve asset directly.

![image](./image.png)

---

## 2. The approach: formula → AnimationCurve

### 2.1 Tool entry point

From the Unity menu bar: `Assets → Create → xxx / Curve`, which opens a dedicated editor window.

The window has only two input fields:

- **Formula text**: one or more lines of math expressions in JS syntax
- **Key point count**: sampling precision (default 20)

Click `Create`, the curve is generated, and it's written straight into project assets.

![curve tool 1](./curve tool 1.jpeg)

### 2.2 Input and output


| Input | Description | Example |
| ----- | ---------------------------------- | --------------------- |
| Formula text | Math expression in JS syntax; the independent variable is `x` (representing time progress in [0,1]) | `x * x * (3 - 2 * x)` |
| Key point count | Samples N equally spaced points over the [0,1] interval; default 20 | `20` |



| Output | Description |
| -------------- | ---------------------------------- |
| AnimationCurve | Automatically written into Custom Curve Library.asset after generation |


---

## 3. Technical implementation

### 3.1 Core idea: sampling + Jint

Unity's AnimationCurve is essentially a set of keyframes. Given a formula `f(x)`, take N equally spaced points over x ∈ [0, 1], add `(x, f(x))` as keys to the curve, and you get a discretized curve asset.

The key is **formula parsing**. We integrated a JS interpreter (Jint) into the editor tool: the input formula string is executed directly as JS code, with the independent variable `x` injected by the program.

### 3.2 Formula parsing flow

The following is illustrative code:

```csharp
// Formula parsing core
public static AnimationCurve GenerateFromFormula(string formula, int sampleCount)
{
    AnimationCurve curve = new AnimationCurve();
    string jsCode = PrependMathNamespace(formula);
    Engine interpreter = new Engine();
    for (int i = 0; i <= sampleCount; i++)
    {
        float t = i * (1f / sampleCount);        // x ∈ [0, 1]
        float y = interpreter
            .SetValue("x", t)
            .Evaluate(jsCode)
            .ToObject()
            .ToSingle();
        curve.AddKey(t, y);
    }
    return curve;
}

// Math function name completion (cos → Math.cos)
private static string PrependMathNamespace(string str)
{
    string[] mathFuncs = { "E","LN10","LN2","LOG2E","LOG10E","PI","SQRT1_2","SQRT2",
        "abs","acos","acosh","asin","asinh","atan","atanh","atan2","cbrt","ceil",
        "clz32","cos","cosh","exp","expm1","floor","fround","hypot","imul","log",
        "log1p","log10","log2","max","min","pow","random","round","sign","sin",
        "sinh","sqrt","tan","tanh","trunc" };
    foreach (var m in mathFuncs)
        str = Regex.Replace(str, $@"\b{m}\b", $"Math.{m}", RegexOptions.IgnoreCase);
    return str;
}
```

### 3.3 Editor window: menu entry + writing to assets

The following is illustrative code:

```csharp
public class CurveGeneratorWindow : EditorWindow
{
    private string _formulaText = "";
    private int _keyCount = 20;
    private const string _libraryPath = "Assets/.../Custom Curve Library.curves";

    [MenuItem("Assets/Create/xxx/Curve")]
    public static void ShowWindow()
        => GetWindow<CurveGeneratorWindow>("Curve Generator");

    private void OnGUI()
    {
        GUILayout.Label("输入公式:", EditorStyles.boldLabel);
        _formulaText = EditorGUILayout.TextArea(_formulaText, GUILayout.Height(100));

        GUILayout.Label("曲线关键点数量:", EditorStyles.boldLabel);
        _keyCount = EditorGUILayout.IntField(_keyCount);

        if (GUILayout.Button("Create"))
        {
            AnimationCurve curve = CurveTool.GenerateFromFormula(_formulaText, _keyCount);
            if (curve != null)
                SaveToLibrary(curve);
            Close();
        }
    }

    // SerializedObject for writing into the preset library asset
    private void SaveToLibrary(AnimationCurve curve)
    {
        AssetDatabase.Refresh();
        var lib = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>(_libraryPath);
        var so = new SerializedObject(lib);
        var presets = so.FindProperty("m_Presets");
        int idx = presets.arraySize;
        presets.InsertArrayElementAtIndex(idx);
        var item = presets.GetArrayElementAtIndex(idx);
        item.FindPropertyRelative("m_Name").stringValue = "";
        item.FindPropertyRelative("m_Curve").animationCurveValue = curve;
        so.ApplyModifiedProperties();
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
    }
}
```

### 3.4 Typical formulas vs. resulting curve shapes

The tool ships with a whitelist of math function names, automatically completing `sin`, `cos`, `PI` and the like into `Math.sin`, `Math.cos`, `Math.PI`.

> Reference site [inloop/interpolator](https://inloop.github.io/interpolator/): you can verify the curve shape produced by a formula there; the formula syntax the tool supports is fully compatible with it.

![curve tool 3](./curve tool 3.jpeg)

---

## 4. Integration

The tool code lives as an **Editor script**, so it never enters the runtime build. Dependencies:

- `Jint.dll` (the JS interpreter, referenced directly under .NET)
- Unity's built-in `AnimationCurve` and `SerializedObject` APIs

As shown in the code above: the target asset is written to `Assets/.../Custom Curve Library.curves` — an asset file containing multiple curve presets, referenced at runtime by `AECameraAnimationCurve`.

![curve tool 2](./curve tool 2.jpg)

---

## 5. Closing thoughts

By parsing formulas on the fly with a JS interpreter + building keyframes through equal-interval sampling, we turn the formulas handed to us by the artists into usable Unity curve assets — no more hunting for the closest preset curve.

Combined with the AE-minded camera motion module from the previous article, the artists can fine-tune their curve formula in an external tool while engineering simply copies and pastes the parameters. Reproducing HMI motion now requires almost no back-and-forth rework.
