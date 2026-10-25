using System;
using Tizen.NUI;
using Tizen.NUI.BaseComponents;

// Synthetic API shapes only: no Samsung binaries and no claim of native UI
// execution. Compile twice to exercise both loaded-property representations.
namespace Tizen.NUI
{
    public class Vector4
    {
        public readonly float X, Y, Z, W;
        public Vector4(float x, float y, float z, float w)
        { X = x; Y = y; Z = z; W = w; }
    }
    public class Color { }
}
namespace Tizen.NUI.BaseComponents
{
    public class View
    {
#if VECTOR_NUI
        public Vector4 CornerRadius { get; set; }
        public float BorderlineWidth { get; set; }
        public Color BorderlineColor { get; set; }
#else
        public float CornerRadius { get; set; }
#endif
    }
    public class TextLabel : View { }
}

internal static class NuiCompatTests
{
    public static int Main()
    {
        var label = new TextLabel();
        if (!object.ReferenceEquals(label, NuiCompat.Round(label, 18)))
            throw new Exception("Rounding must retain the existing view");
#if VECTOR_NUI
        var radius = label.CornerRadius;
        if (radius.X != 18 || radius.Y != 18 || radius.Z != 18 || radius.W != 18)
            throw new Exception("Per-corner radius was not applied");
#else
        if (label.CornerRadius != 18)
            throw new Exception("Scalar radius was not applied");
#endif
        var color = new Color();
        NuiCompat.Border(label, 4, color);
#if VECTOR_NUI
        if (label.BorderlineWidth != 4 || label.BorderlineColor != color)
            throw new Exception("Available native border was not applied");
        NuiCompat.Border(label, 0, color);
        if (label.BorderlineWidth != 0)
            throw new Exception("Native border was not cleared");
#endif
        Console.WriteLine("NUI radius adaptation and optional border checks passed.");
        return 0;
    }
}
