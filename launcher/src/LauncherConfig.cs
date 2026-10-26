using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.RegularExpressions;

public sealed class InputConfig
{
 public string Name {get;set;}
 public int? SourceId {get;set;}
}

// Independent of Samsung references so mapping and fallback behavior can be tested offline.
public sealed class LauncherConfig
{
 public string Family {get;set;}="frame";
 public List<InputConfig> Inputs {get;set;}=new List<InputConfig>();
 public string ArtModeAppId {get;set;}
 public string NativeHomeAppId {get;set;}
 public string[] DockAppIds {get;set;}=Array.Empty<string>();
 public bool EnablePrivateSettings {get;set;}
 public bool IsFrame => Family=="frame";
 public bool HasInputs => Inputs.Count>0;
 public int HomePage => HasInputs?0:1;
 public bool IsPageAvailable(int page) => page>=HomePage&&page<=2;
 public int ResolvePage(int page) => page==0&&!HasInputs?1:page;
 public int InputIndex(int source) => Inputs.FindIndex(input=>input.SourceId==source);
 public bool IsMapped(int source) => InputIndex(source)>=0;
 public string InputAction(int index) => index>=0&&index<Inputs.Count&&Inputs[index].SourceId.HasValue
  ? "hdmi:"+Inputs[index].SourceId.Value : "unmapped";
 public static LauncherConfig Load(string path)
 {
  var config=JsonSerializer.Deserialize<LauncherConfig>(File.ReadAllText(path));
  if(config==null)throw new InvalidDataException("Launcher configuration is empty.");
  config.Validate();return config;
 }
 public void Validate()
 {
  if(Family!="frame"&&Family!="u8000f")throw new InvalidDataException("Unknown TV family.");
  if(Inputs==null||Inputs.Count>4)throw new InvalidDataException("Configure zero to four inputs.");
  var sources=new HashSet<int>();
  foreach(var input in Inputs)
  {
   if(input==null||string.IsNullOrWhiteSpace(input.Name)||input.Name.Length>40)
    throw new InvalidDataException("Every input needs a short name.");
   if(input.SourceId.HasValue&&(input.SourceId.Value<0||!sources.Add(input.SourceId.Value)))
    throw new InvalidDataException("Source IDs must be nonnegative and unique; use null until verified.");
  }
  ValidateAppId(ArtModeAppId);ValidateAppId(NativeHomeAppId);
  if(DockAppIds==null||DockAppIds.Length>3)throw new InvalidDataException("Configure at most three dock apps.");
  var apps=new HashSet<string>();
  foreach(var id in DockAppIds){ValidateAppId(id);if(string.IsNullOrWhiteSpace(id)||!apps.Add(id))
   throw new InvalidDataException("Dock apps must have unique IDs.");}
 }
 static void ValidateAppId(string id)
 {
  if(id==null)return;
  if(!Regex.IsMatch(id,@"\A[A-Za-z0-9_.-]+\z")||id=="com.samsung.tv.bixby-promotion"||id=="com.samsung.tv.quicklaunch")
   throw new InvalidDataException("Use a verified app ID that does not loop back to Quiet Home or its bridge.");
 }
}
