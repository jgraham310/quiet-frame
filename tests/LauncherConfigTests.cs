using System;
using System.Collections.Generic;
using System.IO;

static class LauncherConfigTests
{
 static void Require(bool condition,string message){if(!condition)throw new Exception(message);}
 public static int Main(string[] args)
 {
  var config=LauncherConfig.Load(args[0]);
  foreach(var request in new[]{null,"", "default", "advertising", "HOME"})
   Require(!LaunchPolicy.Allows("AdPlayer",request),"Unmarked advertising requests must not open Home");
  foreach(var request in new[]{"home","apps","settings"})
   Require(LaunchPolicy.Allows("AdPlayer",request),"Explicit Quiet Home request rejected");
  Require(LaunchPolicy.Allows("BixbyPromotion",null),"Original launch policy is retained explicitly");
  Require(config.IsFrame&&!config.EnablePrivateSettings,"Frame defaults preserve native settings");
  Require(config.ArtModeAppId==null&&config.NativeHomeAppId==null,"No guessed native app IDs");
  Require(config.Inputs.Count==0&&!config.HasInputs&&config.HomePage==1,"Streaming-only defaults open Apps");
  Require(!config.IsPageAvailable(0)&&config.IsPageAvailable(1)&&config.IsPageAvailable(2),"Hidden Inputs cannot receive tab focus");
  Require(!config.IsPageAvailable(-1)&&!config.IsPageAvailable(3),"Tab boundaries stay bounded");
  Require(config.ResolvePage(0)==1&&config.ResolvePage(2)==2,"Inputs shortcut resolves to Apps when no inputs exist");
  Require(config.InputIndex(0)==-1&&!config.IsMapped(0)&&config.InputAction(0)=="unmapped", "TV source is not inferred to be HDMI");
  config.Inputs=new List<InputConfig>{new InputConfig{Name="A"},new InputConfig{Name="B"},new InputConfig{Name="C"},new InputConfig{Name="D"}};
  config.Validate();
  Require(config.HasInputs&&config.HomePage==0&&config.IsPageAvailable(0),"Configured inputs restore the Inputs page");
  for(int i=0;i<4;i++)Require(config.InputAction(i)=="unmapped","Unknown source cannot switch inputs");
  config.Inputs[0].SourceId=37;config.Inputs[3].SourceId=42;config.Validate();
  Require(config.InputIndex(42)==3&&config.InputAction(0)=="hdmi:37","Arbitrary verified source mapping");
  Require(!config.IsMapped(14)&&config.InputIndex(-1)==-1,"Unmapped Back cannot fall back to U8000F sources");
  var temporary=Path.GetTempFileName();
  try{
   foreach(var json in new[]{
    "null", "{\"Inputs\":null}",
    "{\"Inputs\":[{\"Name\":\"1\"},{\"Name\":\"2\"},{\"Name\":\"3\"},{\"Name\":\"4\"},{\"Name\":\"5\"}]}",
    "{\"Inputs\":[{\"Name\":\"A\",\"SourceId\":-1}]}",
    "{\"Inputs\":[{\"Name\":\"A\",\"SourceId\":37},{\"Name\":\"B\",\"SourceId\":37}]}",
    "{\"Inputs\":[null]}", "{\"Family\":\"other\"}",
    "{\"NativeHomeAppId\":\"com.samsung.tv.bixby-promotion\"}",
    "{\"ArtModeAppId\":\"com.samsung.tv.quicklaunch\"}",
    "{\"DockAppIds\":[\"a\",\"a\"]}", "{\"ArtModeAppId\":\"\"}",
    "{\"ArtModeAppId\":\"example.app\\n\"}"}){
    File.WriteAllText(temporary,json);bool rejected=false;
    try{LauncherConfig.Load(temporary);}catch(InvalidDataException){rejected=true;}
    Require(rejected,"Invalid configuration accepted: "+json);
   }
   File.WriteAllText(temporary,"{\"Family\":\"u8000f\",\"Inputs\":[{\"Name\":\"Console\",\"SourceId\":14}],\"EnablePrivateSettings\":true}");
   Require(!LauncherConfig.Load(temporary).IsFrame,"Original TV remains configurable explicitly");
   File.WriteAllText(temporary,"{\"Inputs\":[]}");
   Require(LauncherConfig.Load(temporary).HomePage==1,"Explicit empty input list opens Apps");
  }finally{File.Delete(temporary);}
  Console.WriteLine("Streaming-only defaults, page availability, verified inputs and invalid configuration checks passed.");
  return 0;
 }
}
