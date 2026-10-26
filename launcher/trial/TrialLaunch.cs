using System;
using System.Runtime.InteropServices;

// Short-lived app-control sender, kept outside the repurposed package.
// It never changes Home, source or power preferences.
public static class TrialLaunch
{
 [DllImport("libc.so.6")] static extern uint getuid();
 [DllImport("libc.so.6")] static extern uint geteuid();
 [DllImport("libc.so.6")] static extern uint getgid();
 [DllImport("libc.so.6")] static extern uint getegid();
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_create(out IntPtr c);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_set_app_id(IntPtr c,string id);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_set_operation(IntPtr c,string op);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_add_extra_data(IntPtr c,string key,string value);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_send_launch_request(IntPtr c,IntPtr cb,IntPtr data);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_destroy(IntPtr c);

 public interface IControl {
  int Create(out IntPtr c); int SetId(IntPtr c,string id); int SetOperation(IntPtr c,string operation);
  int AddExtra(IntPtr c,string key,string value); int Send(IntPtr c); int Destroy(IntPtr c);
 }
 sealed class NativeControl : IControl {
  public int Create(out IntPtr c)=>app_control_create(out c);
  public int SetId(IntPtr c,string id)=>app_control_set_app_id(c,id);
  public int SetOperation(IntPtr c,string op)=>app_control_set_operation(c,op);
  public int AddExtra(IntPtr c,string key,string value)=>app_control_add_extra_data(c,key,value);
  public int Send(IntPtr c)=>app_control_send_launch_request(c,IntPtr.Zero,IntPtr.Zero);
  public int Destroy(IntPtr c)=>app_control_destroy(c);
 }
 public static bool ValidPage(string page) => page=="home"||page=="apps"||page=="settings";
 public static int Request(IControl api,string page,bool checkOnly) {
  if(!checkOnly&&!ValidPage(page))return 2;
  IntPtr control;int result=api.Create(out control);
  Console.WriteLine("app_control_create="+result);
  if(result!=0)return 1;
  try {
   if(checkOnly){Console.WriteLine("App-control handle verified; no launch request sent.");return 0;}
   result=api.SetId(control,"com.samsung.tv.adplayer");
   if(result==0)result=api.SetOperation(control,"http://tizen.org/appcontrol/operation/default");
   if(result==0)result=api.AddExtra(control,"quiet_page",page);
   if(result==0)result=api.Send(control);
   Console.WriteLine("quiet_home_launch_result="+result);
   return result==0?0:1;
  }finally{api.Destroy(control);}
 }
 public static int Main(string[] args)
 {
  try {
   uint uid,gid;
   if(args.Length<3||!uint.TryParse(args[1],out uid)||uid==0||!uint.TryParse(args[2],out gid)
      ||(args[0]=="check"?args.Length!=3:args[0]!="launch"||args.Length!=4||!ValidPage(args[3])))return 2;
   Console.WriteLine("helper_uid="+getuid()+" helper_euid="+geteuid()+" helper_gid="+getgid()+" helper_egid="+getegid());
   if(getuid()!=uid||geteuid()!=uid||getgid()!=gid||getegid()!=gid)return 3;
   return Request(new NativeControl(),args.Length==4?args[3]:null,args[0]=="check");
  }catch(Exception error){Console.WriteLine(error.GetType().Name+": "+error.Message);return 1;}
 }
}
