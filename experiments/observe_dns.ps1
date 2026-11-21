param([int]$DurationSeconds = 1200)

$targetName = 'app.mcf.todicode.tech'
$authoritativeIp = [Net.Dns]::GetHostAddresses('ns-1064.awsdns-05.org') |
    Where-Object AddressFamily -eq 'InterNetwork' |
    Select-Object -First 1 -ExpandProperty IPAddressToString

if (-not $authoritativeIp) {
    throw 'No IPv4 address found for the Route 53 nameserver.'
}

'utc,source,result'
$timer = [Diagnostics.Stopwatch]::StartNew()

while ($timer.Elapsed.TotalSeconds -lt $DurationSeconds) {
    $reply = nslookup.exe -timeout=2 -retry=1 -type=CNAME $targetName $authoritativeIp 2>$null |
        Select-String 'canonical name\s*=\s*(\S+)' |
        Select-Object -First 1

    $cname = 'lookup_error'
    if ($reply) {
        $cname = $reply.Matches[0].Groups[1].Value.TrimEnd([char]'.')
    }
    '{0:o},route53_authoritative,{1}' -f [DateTimeOffset]::UtcNow, $cname

    $cachedIp = 'cache_miss'
    try {
        $address = Resolve-DnsName -Name $targetName -Type A -CacheOnly -ErrorAction Stop |
            Where-Object Type -eq 'A' |
            Select-Object -First 1 -ExpandProperty IPAddress
        if ($address) {
            $cachedIp = $address
        }
    } catch {
        $cachedIp = 'cache_miss'
    }
    '{0:o},windows_dns_cache,{1}' -f [DateTimeOffset]::UtcNow, $cachedIp

    Start-Sleep -Seconds 2
}