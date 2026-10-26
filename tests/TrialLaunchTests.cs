using System;
using System.Collections.Generic;
public static class TrialLaunchTests {
 sealed class Fake : TrialLaunch.IControl {
  public readonly List<string> Calls=new List<string>();
  public string Fail="",Throw="";
  int Step(string name){Calls.Add(name);if(Throw==name)throw new Exception("synthetic");return Fail==name?-9:0;}
  public int Create(out IntPtr c){c=new IntPtr(42);return Step("create");}
  public int SetId(IntPtr c,string id){if(id!="com.samsung.tv.adplayer")throw new Exception("wrong target");return Step("id");}
  public int SetOperation(IntPtr c,string operation){if(operation!="http://tizen.org/appcontrol/operation/default")throw new Exception("wrong operation");return Step("operation");}
  public int AddExtra(IntPtr c,string key,string value){if(key!="quiet_page"||value!="home")throw new Exception("wrong marker");return Step("extra");}
  public int Send(IntPtr c)=>Step("send");
  public int Destroy(IntPtr c)=>Step("destroy");
 }
 static void Check(bool ok){if(!ok)throw new Exception("Trial launch check failed");}
 public static int Main(){
  var api=new Fake();Check(TrialLaunch.Request(api,null,true)==0);Check(string.Join(",",api.Calls)=="create,destroy");
  api=new Fake();Check(TrialLaunch.Request(api,"unmarked",false)==2);Check(api.Calls.Count==0);
  api=new Fake();Check(TrialLaunch.Request(api,"home",false)==0);Check(string.Join(",",api.Calls)=="create,id,operation,extra,send,destroy");
  foreach(var failure in new[]{"create","id","operation","extra","send"}){
   api=new Fake{Fail=failure};Check(TrialLaunch.Request(api,"home",false)==1);
   Check(api.Calls.Contains("destroy")== (failure!="create"));
   if(failure!="send")Check(!api.Calls.Contains("send"));
  }
  api=new Fake{Throw="operation"};try{TrialLaunch.Request(api,"home",false);throw new Exception("Expected error");}catch(Exception e){Check(e.Message=="synthetic");}
  Check(api.Calls[api.Calls.Count-1]=="destroy");
  foreach(var args in new[]{new string[0],new[]{"launch","0","100","home"},new[]{"launch","1234","100","unexpected"},new[]{"check","1234","100","extra"}})Check(TrialLaunch.Main(args)==2);
  Console.WriteLine("Trial launch failure/cleanup checks passed; native APIs were stubbed.");return 0;
 }
}
