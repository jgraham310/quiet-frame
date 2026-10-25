using System;
using System.Reflection;
using Tizen.NUI;
using Tizen.NUI.BaseComponents;

// Samsung's NUI revisions expose scalar or per-corner radii independently of
// the CLR target. Inspect the loaded API instead of inferring it from .NET.
internal static class NuiCompat
{
    private static readonly PropertyInfo Radius = typeof(View).GetProperty("CornerRadius");
    private static readonly PropertyInfo BorderWidth = typeof(View).GetProperty("BorderlineWidth");
    private static readonly PropertyInfo BorderColor = typeof(View).GetProperty("BorderlineColor");

    internal static T Round<T>(T view, float radius) where T : View
    {
        if (Radius == null || !Radius.CanWrite)
            return view;
        if (Radius.PropertyType == typeof(float))
            Radius.SetValue(view, radius);
        else if (Radius.PropertyType == typeof(Vector4))
            Radius.SetValue(view, new Vector4(radius, radius, radius, radius));
        return view;
    }

    // Optional decoration only. Focus also uses scale/labels and the app grid
    // has an SVG outline, so absent native border properties never hide focus.
    internal static void Border(View view, float width, Color color)
    {
        if (BorderWidth != null && BorderWidth.CanWrite
            && BorderWidth.PropertyType == typeof(float)
            && BorderColor != null && BorderColor.CanWrite
            && BorderColor.PropertyType == typeof(Color))
        {
            BorderWidth.SetValue(view, width);
            BorderColor.SetValue(view, color);
        }
    }
}
