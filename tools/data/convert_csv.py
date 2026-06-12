import csv
import sys
import glob
import os

def convert_file(filepath):
    out_filepath = filepath.replace(".csv", "_decoded.csv")
    if filepath == out_filepath:
        return
        
    print(f"Converting {filepath} -> {out_filepath}")
    
    with open(filepath, 'r') as fin, open(out_filepath, 'w', newline='') as fout:
        reader = csv.DictReader(fin)
        
        # Keep original fieldnames
        fieldnames = reader.fieldnames
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in reader:
            # Extract 16-bit parsed DACs
            d0_16 = int(row['DAC0'])
            d1_16 = int(row['DAC1'])
            d2_16 = int(row['DAC2'])
            d3_16 = int(row['DAC3'])
            d4_16 = int(row['DAC4'])
            d5_16 = int(row['DAC5'])
            
            # Reconstruct w0, w1, w2
            w0 = (d1_16 << 16) | d0_16
            w1 = (d3_16 << 16) | d2_16
            w2 = (d5_16 << 16) | d4_16
            
            # Reparse to 12-bit logic
            dac0 = w0 & 0xFFF
            dac1 = (w0 >> 12) & 0xFFF
            dac2 = ((w0 >> 24) & 0xFF) | ((w1 & 0xF) << 8)
            dac3 = (w1 >> 4) & 0xFFF
            dac4 = (w1 >> 16) & 0xFFF
            dac5 = ((w1 >> 28) & 0xF) | ((w2 & 0xFF) << 4)
            dac6 = (w2 >> 8) & 0xFFF
            dac7 = (w2 >> 20) & 0xFFF
            
            row['DAC0'] = dac0
            row['DAC1'] = dac1
            row['DAC2'] = dac2
            row['DAC3'] = dac3
            row['DAC4'] = dac4
            row['DAC5'] = dac5
            row['DAC6'] = dac6
            row['DAC7'] = dac7
            
            # Correct J+ and J- (revert sign-extension)
            jp = int(row['J+'])
            jm = int(row['J-'])
            
            if jp < 0: jp += 0x10000
            if jm < 0: jm += 0x10000
                
            row['J+'] = jp
            row['J-'] = jm
            
            writer.writerow(row)

if __name__ == '__main__':
    csv_files = glob.glob("*.csv")
    for f in csv_files:
        if not f.endswith("_decoded.csv"):
            convert_file(f)
    print("Done!")
