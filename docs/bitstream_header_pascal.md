# BitGrid LUT bitstream header — Pascal/Delphi reference

This page documents the fixed header for BitGrid LUT bitstreams and provides a compact Pascal/Delphi record and loader sketch for quick interop.

## Header layout (little‑endian)

Offset  Size  Type    Name             Notes
- 0      4     char    magic            'B','G','B','S'
- 4      2     u16     version          1
- 6      2     u16     header_size      24
- 8      2     u16     width            cells
- 10     2     u16     height           cells
- 12     1     u8      order            0=row, 1=col, 2=snake
- 13     1     u8      flags            bit0=0 means LUT bits are LSB‑first
- 14     4     u32     payload_bits     width*height*4*16
- 18     4     u32     payload_crc32    CRC‑32 (IEEE) of payload bytes
- 22     2     u16     reserved         0
- 24     …     u8[]    payload          packed LUT bits

Notes
- Endianness: little‑endian for all multi‑byte fields.
- Payload length in bytes = (payload_bits + 7) div 8.
- CRC covers payload only (not the header).

## Pascal packed record

```pascal
unit BitGridBitstream;

interface

type
  TBitGridBitstreamHeader = packed record
    Magic: array[0..3] of AnsiChar; // 'B','G','B','S'
    Version: Word;                  // 1
    HeaderSize: Word;               // 24
    Width: Word;                    // cells
    Height: Word;                   // cells
    Order: Byte;                    // 0=row,1=col,2=snake
    Flags: Byte;                    // bit0=0 => LUT bits LSB-first
    PayloadBits: LongWord;          // total bits in payload
    PayloadCRC32: LongWord;         // CRC32(IEEE) of payload
    Reserved: Word;                 // 0
  end;

const
  BGBS_MAGIC: array[0..3] of AnsiChar = ('B','G','B','S');
  BGBS_VERSION = 1;
  BGBS_HEADER_SIZE = SizeOf(TBitGridBitstreamHeader); // should be 24

  // Scan order codes
  BGBS_ORDER_ROW_MAJOR = 0;
  BGBS_ORDER_COL_MAJOR = 1;
  BGBS_ORDER_SNAKE     = 2;

implementation

end.
```

The `packed record` enforces 1‑byte alignment, matching the on‑disk layout.

## Minimal loader sketch

```pascal
uses SysUtils, Classes
{$IFDEF FPC}
  , zstream // or any unit that exposes crc32; optional
{$ENDIF}
;

function ReadHeader(const FileName: string; out H: TBitGridBitstreamHeader; out Payload: TBytes): Boolean;
var
  FS: TFileStream;
  PayloadBytes: NativeUInt;
  CalcCRC: LongWord;
begin
  Result := False;
  FS := TFileStream.Create(FileName, fmOpenRead or fmShareDenyNone);
  try
    if FS.Read(H, SizeOf(H)) <> SizeOf(H) then Exit;
    if (H.Magic <> BGBS_MAGIC) then Exit;
    if (H.Version <> BGBS_VERSION) then Exit;
    if (H.HeaderSize <> SizeOf(H)) then Exit;
    PayloadBytes := (H.PayloadBits + 7) div 8;
    SetLength(Payload, PayloadBytes);
    if FS.Read(Payload[0], PayloadBytes) <> Integer(PayloadBytes) then Exit;
    // Optional: verify CRC32 (IEEE). If you have zlib, use crc32(). Otherwise, substitute your CRC32.
    {$IFDEF FPC}
    CalcCRC := crc32(0, @Payload[0], PayloadBytes);
    {$ELSE}
    CalcCRC := 0; // TODO: compute CRC32; skip check if not available
    {$ENDIF}
    if (CalcCRC <> 0) and (CalcCRC <> H.PayloadCRC32) then Exit;
    Result := True;
  finally
    FS.Free;
  end;
end;
```

If you don’t have `crc32`, you can temporarily skip the check while bringing up the reader; the Python inspector (`bitgrid.cli.bitstream_inspect`) can validate files for you.

## Interpreting the payload

- Per cell: outputs in order [N, E, S, W].
- Per output: 16‑bit LUT, packed LSB‑first (bit i corresponds to input index `i = N | (E shl 1) | (S shl 2) | (W shl 3)`).
- Cells are scanned by `order`:
  - row‑major: for y := 0..H-1 do for x := 0..W-1 do …
  - col‑major: for x := 0..W-1 do for y := 0..H-1 do …
  - snake: row‑major, but odd rows traverse x from W-1 downto 0.

Pseudo‑decode

```pascal
var bitIdx, i, k, lutBit: Integer; cellLUTs: array[0..3] of Word;
bitIdx := 0;
for y := 0 to H-1 do
begin
  for x := 0 to W-1 do
  begin
    // optionally reverse x on odd rows for snake order
    for k := 0 to 3 do
    begin
      cellLUTs[k] := 0;
      for i := 0 to 15 do
      begin
        // Read next bit (LSB-first across bytes)
        lutBit := (Payload[bitIdx div 8] shr (bitIdx and 7)) and 1;
        if lutBit <> 0 then
          cellLUTs[k] := cellLUTs[k] or (1 shl i);
        Inc(bitIdx);
      end;
    end;
    // cellLUTs now holds [N,E,S,W] 16-bit LUTs for (x,y)
  end;
end;
```

## Sanity checks

- Payload length must be exactly `(width*height*4*16 + 7) div 8` bytes.
- If CRC32 is available, compare to header’s `payload_crc32`.
- `header_size` should be 24 and `version` should be 1.

## See also

- Python inspector: `python -m bitgrid.cli.bitstream_inspect file.bin`
- Python packer with header: `python -m bitgrid.cli.bitstream_roundtrip --header ...`
- Emulator loader: `python -m bitgrid.cli.emu_load_bitstream ...`
