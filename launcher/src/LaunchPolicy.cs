// A reused advertising identity must not turn ordinary vendor requests into
// Home launches. The assembly name is compiled, not read from mutable assets.
public static class LaunchPolicy
{
 public static bool RequiresMarker(string assembly) => assembly=="AdPlayer";
 public static bool Allows(string assembly,string page) => !RequiresMarker(assembly)
  ||page=="home"||page=="apps"||page=="settings";
}
