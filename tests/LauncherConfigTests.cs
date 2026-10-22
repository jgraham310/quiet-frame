using System;
using System.IO;

static class LauncherConfigTests
{
 static void Require(bool condition,string message){if(!condition)throw new Exception(message);}
 public static int Main(string[] args)
 {
  var config=LauncherConfig.Load(args[0]);
  Require(config.IsFrame&&!config.EnablePrivateSettings,"Frame defaults preserve native settings");
  Require(config.ArtModeAppId==null&&config.NativeHomeAppId==null,"No guessed native app IDs");
  Require(config.Inputs.Count==4&&!config.IsMapped(13),"Four inputs, no inferred source IDs");
  for(int i=0;i<4;i++)Require(config.InputAction(i)=="unmapped","Unknown source cannot switch inputs");
  config.Inputs[0].SourceId=37;config.Inputs[3].SourceId=42;config.Validate();
  Require(config.InputIndex(42)==3&&config.InputAction(0)=="hdmi:37","Arbitrary verified source mapping");
  Require(!config.IsMapped(14)&&config.InputIndex(-1)==-1,"Unmapped Back cannot fall back to U8000F sources");
  var temporary=Path.GetTempFileName();
  try{
   foreach(var json in new[]{
    "null", "{\"Inputs\":[]}", "{\"Inputs\":null}",
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
  }finally{File.Delete(temporary);}
  Console.WriteLine("Frame defaults, verified inputs, fallback and invalid configuration checks passed.");
  return 0;
 }
}
