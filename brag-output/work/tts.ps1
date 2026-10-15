param([int]$Rate = -1)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$work = Split-Path -Parent $MyInvocation.MyCommand.Path
$json = Get-Content -Raw -Encoding UTF8 (Join-Path $work 'narration.json') | ConvertFrom-Json
$out = Join-Path $work 'audio'
New-Item -ItemType Directory -Force $out | Out-Null
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(44100, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$n = 0
foreach ($sc in $json) {
  $i = 0
  foreach ($s in $sc.sentences) {
    $i++
    $text = if ($s.PSObject.Properties.Name -contains 's' -and $s.s) { $s.s } else { $s.t }
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $synth.SelectVoice('Microsoft Maria Desktop')
    $synth.Rate = $Rate
    $synth.Volume = 100
    $file = Join-Path $out ("{0}_{1:00}.wav" -f $sc.id, $i)
    $synth.SetOutputToWaveFile($file, $fmt)
    $synth.Speak($text)
    $synth.Dispose()
    $n++
  }
}
"generated $n wav files"
