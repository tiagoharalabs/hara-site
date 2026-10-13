Check 'wrapped_websocket_transport_class' {
 $ws=[Net.WebSockets.WebSocketException]::new([Net.WebSockets.WebSocketError]::ConnectionClosedPrematurely)
 $io=[IO.IOException]::new('fixture private message',$ws)
 $outer=[Management.Automation.MethodInvocationException]::new('fixture private message',$io)
 $er=[pscustomobject]@{Exception=$outer}
 if((Get-EventV2TransportErrorClass $er)-ne'WEBSOCKET_CONNECTIONCLOSEDPREMATURELY'){throw 'WEBSOCKET_CLASS'}
 if((Get-SafeErrorCode $er)-ne'METHODINVOCATIONEXCEPTION'){throw 'ORIGINAL_CODE_CHANGED'}
}
Check 'wrapped_socket_transport_class' {
 $socket=[Net.Sockets.SocketException]::new(10054)
 $io=[IO.IOException]::new('fixture private message',$socket)
 $outer=[Management.Automation.MethodInvocationException]::new('fixture private message',$io)
 if((Get-EventV2TransportErrorClass ([pscustomobject]@{Exception=$outer}))-ne'SOCKET_CONNECTIONRESET'){throw 'SOCKET_CLASS'}
}
Check 'unknown_transport_message_not_persisted' {
 $unknown=[Exception]::new('fixture private path and customer payload')
 $value=Get-EventV2TransportErrorClass ([pscustomobject]@{Exception=$unknown})
 if($value-ne'UNKNOWN'){throw 'UNKNOWN_CLASS_NOT_SANITIZED'}
}
Check 'transport_class_chain_depth_bounded' {
 $ex=[Net.Sockets.SocketException]::new(10054)
 foreach($i in 1..9){$ex=[IO.IOException]::new('fixture private message',$ex)}
 if((Get-EventV2TransportErrorClass ([pscustomobject]@{Exception=$ex}))-ne'UNKNOWN'){throw 'DEPTH_NOT_BOUNDED'}
}
Check 'original_code_and_safe_class_persisted' {
 Set-EventV2Status -Connected $false -ErrorCode 'METHODINVOCATIONEXCEPTION' -TransportErrorClass 'SOCKET_CONNECTIONRESET'
 $value=Get-Content -Raw -LiteralPath $EventStatus|ConvertFrom-Json
 if($value.last_error_code-ne'METHODINVOCATIONEXCEPTION'-or$value.transport_error_class-ne'SOCKET_CONNECTIONRESET'){throw 'STATUS_CLASS'}
 Set-EventV2Status -Connected $true
 $value=Get-Content -Raw -LiteralPath $EventStatus|ConvertFrom-Json
 if($value.transport_error_class-ne'SOCKET_CONNECTIONRESET'){throw 'SAFE_CLASS_LOST_ON_RECOVERY'}
}
