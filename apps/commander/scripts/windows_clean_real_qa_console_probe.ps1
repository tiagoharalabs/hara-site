$ErrorActionPreference='Stop'
$Root='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1'
if(([string](Get-CimInstance Win32_ComputerSystemProduct).UUID).ToLowerInvariant() -cne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba'){throw 'CLONE_UUID_REQUIRED'}
if([Security.Principal.WindowsIdentity]::GetCurrent().Name -notmatch '\\HARAQA$'){throw 'REAL_QA_REQUIRED'}
$box=Join-Path $Root ('console-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $box|Out-Null
Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
public static class CleanConsoleInput {
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
 public static int Launch(string command){STARTUPINFO s=new STARTUPINFO();s.cb=Marshal.SizeOf(s);s.flags=1;s.show=1;PROCESS_INFORMATION p;if(!CreateProcessW(null,new StringBuilder(command),IntPtr.Zero,IntPtr.Zero,false,16,IntPtr.Zero,null,ref s,out p))throw new Win32Exception(Marshal.GetLastWin32Error());CloseHandle(p.process);CloseHandle(p.thread);return p.pid;}
 public static bool Type(int pid,string text){IntPtr output=GetStdHandle(-11),error=GetStdHandle(-12);FreeConsole();bool attached=false;for(int n=0;n<30;n++){if(AttachConsole(pid)){attached=true;break;}System.Threading.Thread.Sleep(100);}if(!attached){SetStdHandle(-11,output);SetStdHandle(-12,error);return false;}try{INPUT_RECORD[] keys=new INPUT_RECORD[text.Length];for(int i=0;i<text.Length;i++){keys[i].type=1;keys[i].down=1;keys[i].repeat=1;keys[i].ch=text[i];keys[i].virtualKey=(short)(text[i]=='\r'?13:0);}int written;return WriteConsoleInputW(GetStdHandle(-10),keys,keys.Length,out written)&&written==keys.Length;}finally{FreeConsole();SetStdHandle(-11,output);SetStdHandle(-12,error);}}
}
'@
$file=Join-Path $box 'read-secure.ps1';$out=Join-Path $box 'result.json'
$body='$s=Read-Host "Pairing fixture" -AsSecureString;$b=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s);try{$r=[ordered]@{chars=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($b).Length;secure=($s -is [Security.SecureString])};[IO.File]::WriteAllText("'+$out+'",($r|ConvertTo-Json -Compress))}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b)}'
[IO.File]::WriteAllText($file,$body,(New-Object Text.UTF8Encoding($false)))
$exe=(Get-Command powershell.exe).Source
$child=[CleanConsoleInput]::Launch('"'+$exe+'" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "'+$file+'"')
try{
 Start-Sleep -Milliseconds 1200
 $typed=[CleanConsoleInput]::Type($child,"HARA-QA-SECURE-INPUT`r")
 $deadline=[DateTime]::UtcNow.AddSeconds(7)
 while([DateTime]::UtcNow -lt $deadline -and -not(Test-Path -LiteralPath $out)){Start-Sleep -Milliseconds 100}
 $result=if(Test-Path -LiteralPath $out){Get-Content -LiteralPath $out -Raw|ConvertFrom-Json}else{$null}
 [ordered]@{schema='hara.windows-clean-console-input-probe.v1';state=if($typed -and $result -and $result.chars -eq 20 -and $result.secure){'PASS'}else{'FAIL'};native_console_write_success=$typed;secure_readhost_completed=[bool]$result;chars=if($result){$result.chars}else{$null};secure=if($result){$result.secure}else{$null};synthetic_input_only=$true;real_pairing_token_used=$false;main_agent_or_task_touched=$false;qa_identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name;actual_qa_localappdata=$env:LOCALAPPDATA}|ConvertTo-Json -Compress|Set-Content -LiteralPath (Join-Path $Root 'native-qa-console-secure-input.json') -Encoding UTF8
}finally{
 $p=Get-Process -Id $child -ErrorAction SilentlyContinue;if($p){Stop-Process -Id $child -Force -ErrorAction SilentlyContinue}
 Remove-Item -LiteralPath $box -Recurse -Force -ErrorAction SilentlyContinue
}
