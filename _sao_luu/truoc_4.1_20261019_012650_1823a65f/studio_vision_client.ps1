function Invoke-NblVisionProbe($Lease,[bool]$FreshAlerts=$false) {
  $client=[Net.Sockets.TcpClient]::new()
  try {
   $client.SendTimeout=3000;$client.ReceiveTimeout=30000
   $client.Connect('127.0.0.1',[int]$Lease.port)
   $stream=$client.GetStream()
   $utf8=[Text.UTF8Encoding]::new($false)
   $writer=[IO.StreamWriter]::new($stream,$utf8,1024,$true);$writer.AutoFlush=$true
   $reader=[IO.StreamReader]::new($stream,$utf8,$false,1024,$true)
   $request=@{token=[string]$Lease.token;lease=[string]$Lease.lease;fresh=$FreshAlerts}|ConvertTo-Json -Compress
   $writer.WriteLine($request)
   $line=$reader.ReadLine()
   if(-not $line -or $line.Length -gt 50000){throw 'Invalid OCR probe response'}
   $reply=$line|ConvertFrom-Json
   if(-not $reply.ok){throw ([string]$reply.error)}
   return $reply.result
  }finally{$client.Dispose()}
}
