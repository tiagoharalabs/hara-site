Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
public static class CleanConsoleInput {
 static System.Collections.Generic.Dictionary<int,IntPtr> Handles=new System.Collections.Generic.Dictionary<int,IntPtr>();
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool GetExitCodeProcess(IntPtr process,out uint code);
 public static int ExitCode(int pid){uint code;if(!GetExitCodeProcess(Handles[pid],out code))throw new Win32Exception(Marshal.GetLastWin32Error());return (int)code;}
 public static void Release(int pid){if(Handles.ContainsKey(pid)){CloseHandle(Handles[pid]);Handles.Remove(pid);}}
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] public struct STARTUPINFO {public int cb;public string reserved;public string desktop;public string title;public int x,y,xsize,ysize,xchars,ychars,fill,flags;public short show,reserved2;public IntPtr reservedPtr,input,output,error;}
 [StructLayout(LayoutKind.Sequential)] public struct PROCESS_INFORMATION {public IntPtr process,thread;public int pid,tid;}
 [StructLayout(LayoutKind.Explicit,CharSet=CharSet.Unicode)] public struct INPUT_RECORD {[FieldOffset(0)]public short type;[FieldOffset(4)]public int down;[FieldOffset(8)]public short repeat;[FieldOffset(10)]public short virtualKey;[FieldOffset(12)]public short scan;[FieldOffset(14)]public char ch;[FieldOffset(16)]public int controls;}
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern bool CreateProcessW(string app,StringBuilder command,IntPtr p,IntPtr t,bool inherit,uint flags,IntPtr environment,string directory,ref STARTUPINFO startup,out PROCESS_INFORMATION info);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool AttachConsole(int pid);
 [DllImport("kernel32.dll")]static extern bool FreeConsole();
 [DllImport("kernel32.dll")]static extern IntPtr GetStdHandle(int id);
 [DllImport("kernel32.dll")]static extern bool SetStdHandle(int id,IntPtr handle);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern bool WriteConsoleInputW(IntPtr input,INPUT_RECORD[] events,int count,out int written);
 [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr handle);
 public static int Launch(string command){STARTUPINFO s=new STARTUPINFO();s.cb=Marshal.SizeOf(s);s.flags=1;s.show=1;PROCESS_INFORMATION p;if(!CreateProcessW(null,new StringBuilder(command),IntPtr.Zero,IntPtr.Zero,false,16,IntPtr.Zero,null,ref s,out p))throw new Win32Exception(Marshal.GetLastWin32Error());Handles[p.pid]=p.process;CloseHandle(p.thread);return p.pid;}
 public static bool Type(int pid,string text){IntPtr output=GetStdHandle(-11),error=GetStdHandle(-12);FreeConsole();bool attached=false;for(int n=0;n<30;n++){if(AttachConsole(pid)){attached=true;break;}System.Threading.Thread.Sleep(100);}if(!attached){SetStdHandle(-11,output);SetStdHandle(-12,error);return false;}try{INPUT_RECORD[] keys=new INPUT_RECORD[text.Length];for(int i=0;i<text.Length;i++){keys[i].type=1;keys[i].down=1;keys[i].repeat=1;keys[i].ch=text[i];keys[i].virtualKey=(short)(text[i]=='\r'?13:0);}int written;return WriteConsoleInputW(GetStdHandle(-10),keys,keys.Length,out written)&&written==keys.Length;}finally{FreeConsole();SetStdHandle(-11,output);SetStdHandle(-12,error);}}
}
'@
