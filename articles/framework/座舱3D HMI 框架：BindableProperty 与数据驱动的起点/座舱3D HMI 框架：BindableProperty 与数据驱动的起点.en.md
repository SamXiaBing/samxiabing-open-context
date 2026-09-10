---
title: "Cockpit 3D HMI Framework: BindableProperty and the Starting Point of Data-Driven Design"
lang: en
date: 2026-08-07
series: framework
no: 
status: published
visibility: public
wechat_url: ""
---

> In development, the most typical scenario is: a signal arrives, tied to a value change; the value changes, tied to the animation of a specific part. For this scenario, registering an event for every signal and throwing that event when the signal arrives does work. But is there a more convenient approach — one that at least feels better to use?

There is. During framework development, you can use a mechanism that binds to specific variables and, once bound, comes with a registrable delegate built in. Its name is `BindableProperty<T>` — a very lightweight but very useful class that takes on the duty of automatically notifying all registrants the moment the value changes. It appears in quite a few frameworks, and we've kept using it as well.

---

# Design and Implementation

## If I Don't Use It?

Without it, in the tightly-coupled style, you might write:

```csharp
private DayNightMode _mode;
public DayNightMode Mode
{
    get => _mode;
    set
    {
        if (_mode == value) return;
        _mode = value;
        RefreshUI();          // manual call
        UpdateSceneLight();   // manual call
        NotifyAnimations();   // manual call
    }
}
```

The problem: after `Mode` changes, who exactly gets notified — whoever writes the setter has to know. If a module is added later that also needs to respond to mode changes, you have to come back and modify this setter. Every new responder means one more line of code. In multi-person collaboration, it's a disaster.

## Once I Have It!

`BindableProperty<T>`'s approach: **when the value changes, notify only "whoever cares about it", without caring "who needs it"**. The one setting the value just sets it, without worrying about who will respond.

It's a textbook embodiment of the observer pattern, and at the same time it's the basic infrastructure of MVVM.

![Figure 1](./图1.png)

---

## The BindableProperty Code

```csharp
// The following is illustrative code
public class BindableProperty<T>
{
    private T _value = default(T);

    public T Value
    {
        get => _value;
        set
        {
            if (object.Equals(_value, value)) return;   // equality check
            _value = value;
            Apply();                                     // trigger notification
        }
    }

    public void Apply()
    {
        _onValueChangedEvent?.Invoke(_value);
    }

    private event Action<T> _onValueChangedEvent = null;

    public IUnregister RegisterOnValueChanged(Action<T> onValueChanged)
    {
        _onValueChangedEvent += onValueChanged;
        return new Subscription<T>()
        {
            Source = this,
            Callback = onValueChanged
        };
    }

    public void UnRegisterOnValueChanged(Action<T> onValueChanged)
    {
        _onValueChangedEvent -= onValueChanged;
    }
}
```

- The `setter` **checks equality**. `object.Equals(_value, value)` returns immediately when the value hasn't changed, without triggering callbacks — avoiding useless notifications on redundant sets.
- `Apply()` **provides forced triggering**. The delegate can be invoked from outside the class.
- `RegisterOnValueChanged` **returns** `IUnregister`**. This return value is a `Subscription<T>` holding references to the `BindableProperty` and the `Action<T>`, and calling `Unregister()` unsubscribes automatically. This design means the caller doesn't need to remember the specific `BindableProperty` instance — holding an `IUnregister` reference and calling `Unregister()` in `OnDestroy` is enough.

```csharp
// Unsubscription helper class
public class Subscription<T> : IUnregister
{
    public BindableProperty<T> Source { get; set; }
    public Action<T> Callback { get; set; }

    public void Unregister()
    {
        Source.UnRegisterOnValueChanged(Callback);
        Source = null;
        Callback = null;
    }
}
```

---

# How to Use It

Using `BindableProperty<T>` generally takes two steps. Step one, define the properties in the Model:

```csharp
// The following is illustrative code
public class AppModel
{
    public BindableProperty<DayNightMode> DayNightMode = new BindableProperty<DayNightMode>()
    {
        Value = DayNightMode.Day
    };

    public BindableProperty<bool> AppIsPause = new BindableProperty<bool>()
    {
        Value = false
    };
}
```

Step two, register callbacks in the controller that cares about this value:

```csharp
// The following is illustrative code
public abstract class BaseDayNightController : MonoBehaviour
{
    private void Awake()
    {
        var appModel = GetComponent<AppModel>();

        // On initialization, refresh once with the current value
        OnCurrentDayNightModeChanged(appModel.DayNightMode.Value);

        // Register the value-changed callback
        appModel.DayNightMode.RegisterOnValueChanged(OnCurrentDayNightModeChanged);
    }

    private void OnCurrentDayNightModeChanged(DayNightMode dayNightMode)
    {
        switch (dayNightMode)
        {
            case DayNightMode.Day:
                ChangeToDayMode();
                break;
            case DayNightMode.Night:
                ChangeToNightMode();
                break;
        }
    }

    protected virtual void OnDestroy()
    {
        // Unsubscribe on destroy to avoid memory leaks
        var appModel = GetComponent<AppModel>();
        if (appModel != null)
            appModel.DayNightMode.UnRegisterOnValueChanged(OnCurrentDayNightModeChanged);
    }
}
```

In `Awake`, first call `OnCurrentDayNightModeChanged(appModel.DayNightMode.Value)` once, then use `RegisterOnValueChanged` to register for subsequent changes. Making that first call means the controller doesn't sit on the default value — it immediately initializes to the current value.

---

## Closing Thoughts

You could put it this way: everywhere a logical relationship forms between data (the Model layer) and the view (View), `BindableProperty<T>` applies — door state/opening degree, the current system language, the current camera state, and so on. It pulls the question of "who gets notified after the value changes" out of the place where the value is set — the starting point of "data-driven" design.
