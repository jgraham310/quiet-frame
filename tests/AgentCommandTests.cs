using System;
using System.IO;
using System.Reflection;
using System.Text;

internal static class AgentCommandTests
{
    private static readonly MethodInfo Execute = typeof(SamsungTvRootAgent)
        .GetMethod("Execute", BindingFlags.Static | BindingFlags.NonPublic);

    private static string Run(string command)
    {
        // Exercise the production process launcher without starting a callback
        // server, requesting root, or accessing any TV or native Samsung API.
        object result = Execute.Invoke(null, new object[] { command, 5000 });
        Type type = result.GetType();
        const BindingFlags fields = BindingFlags.Instance | BindingFlags.NonPublic;
        int exit = (int)type.GetField("ExitCode", fields).GetValue(result);
        bool timedOut = (bool)type.GetField("TimedOut", fields).GetValue(result);
        string output = Encoding.UTF8.GetString(
            (byte[])type.GetField("StandardOutput", fields).GetValue(result));
        string error = Encoding.UTF8.GetString(
            (byte[])type.GetField("StandardError", fields).GetValue(result));
        if (exit != 0 || timedOut || error.Length != 0)
            throw new Exception("Shell execution failed: exit=" + exit
                + " timeout=" + timedOut + " stderr=" + error);
        return output;
    }

    public static int Main(string[] args)
    {
        string output = Run(@"printf '%s\n' 'one' 'two'
printf '%s\n' 'quote: "" backslash: \'
");
        if (output != "one\ntwo\nquote: \" backslash: \\\n")
            throw new Exception("Quotes, backslashes or newlines changed: " + output);

        output = Run("find . -maxdepth 0 \\( -type d -o -type f \\) -print");
        if (output != ".\n") throw new Exception("Escaped find parentheses changed");

        // Substitute only TV-specific utilities. The exact generated script,
        // including SQL quoting, shell functions and find grouping, is parsed
        // and executed through the production .NET -> setsid -> sh path.
        string stubs = @"
sqlite3() { printf '%s\n' 'synthetic-registry-output'; }
find() { printf '%s\n' '/synthetic/Tizen.NUI.dll'; }
readlink() { printf '%s\n' ""$1""; }
vconftool() {
    case ""$2"" in
        db/appfw/home_appid) printf '%s\n' 'synthetic-home' ;;
        db/appfw/startup_appid)
            printf '%s\n' ""Error: Get: Layer 'system' Key '$2': No such file or directory""
            return 1 ;;
        *) return 99 ;;
    esac
}
";
        output = Run(stubs + File.ReadAllText(args[0]));
        foreach (string expected in new[] {
            "=== Application types ===\n", "=== Home preferences ===\n",
            "synthetic-home\n", "db/appfw/startup_appid: absent (not created)\n",
            "=== Framework assembly paths ===\n", "/synthetic/Tizen.NUI.dll\n",
            "=== Native API library paths ===\n"
        })
            if (!output.Contains(expected))
                throw new Exception("Missing platform output: " + expected);
        Console.WriteLine("Agent shell quoting and full platform script checks passed.");
        return 0;
    }
}
