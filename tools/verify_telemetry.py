import csv
import sys
import argparse

# 8x8 Hadamard Matrix ROM (Sylvester construction)
# 1 represents +1, 0 represents -1 (mapped to +1 and -1 below)
HADAMARD_ROM = [
    [ 1,  1,  1,  1,  1,  1,  1,  1], # Row 0
    [ 1, -1,  1, -1,  1, -1,  1, -1], # Row 1
    [ 1,  1, -1, -1,  1,  1, -1, -1], # Row 2
    [ 1, -1, -1,  1,  1, -1, -1,  1], # Row 3
    [ 1,  1,  1,  1, -1, -1, -1, -1], # Row 4
    [ 1, -1,  1, -1, -1,  1, -1,  1], # Row 5
    [ 1,  1, -1, -1, -1, -1,  1,  1], # Row 6
    [ 1, -1, -1,  1, -1,  1,  1, -1], # Row 7
]

def verify_csv(filename):
    try:
        with open(filename, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        print(f"Error: Could not find file {filename}")
        return
        
    print(f"Loaded {len(rows)} rows from {filename}.")
    if len(rows) < 2:
        print("Need at least 2 rows to verify DAC phase updates.")
        return
        
    errors = 0
    for i in range(len(rows) - 1):
        curr = rows[i]
        nxt = rows[i+1]
        
        try:
            packet = int(curr["Packet"])
            j_plus = int(curr["J+"])
            j_minus = int(curr["J-"])
            delta_j = int(curr["Delta_J"])
            scaled_update = int(curr["Scaled_Update"])
            h_row = int(curr["Hadamard_Row"])
        except ValueError:
            print(f"Skipping row {i} due to parsing error (invalid header?)")
            continue
        
        # ----------------------------------------------------
        # 1. Verify Delta J calculation
        # ----------------------------------------------------
        expected_dj = j_plus - j_minus
        if expected_dj != delta_j:
            print(f"Row {i} (Packet {packet}): Delta J mismatch! HW claims {delta_j}, but J+({j_plus}) - J-({j_minus}) = {expected_dj}")
            errors += 1
            
        # ----------------------------------------------------
        # 2. Verify DAC Step Updates & Dither Directions
        # ----------------------------------------------------
        if scaled_update == 0:
            continue # If step is 0, DACs won't move. Can't deduce dither signs.
            
        expected_rom = HADAMARD_ROM[h_row % 8]
        actual_signs = []
        
        for ch in range(8):
            dac_curr = int(curr[f"DAC{ch}"])
            dac_nxt = int(nxt[f"DAC{ch}"])
            
            diff = dac_nxt - dac_curr
            
            # Catch phase wrapping (V2PI jumps) which artificially makes diff huge
            if abs(diff) > 20000:
                actual_signs.append(None) # Skip this channel's sign check
                continue
                
            # Deduce the applied sign based on which way the DAC moved
            if diff > 0 and scaled_update > 0: actual_signs.append(1)
            elif diff < 0 and scaled_update > 0: actual_signs.append(-1)
            elif diff > 0 and scaled_update < 0: actual_signs.append(-1)
            elif diff < 0 and scaled_update < 0: actual_signs.append(1)
            else: actual_signs.append(0) # DAC didn't move or step size was extremely small
            
            # Verify magnitude matches
            if abs(diff) != abs(scaled_update):
                # Exclude boundary clamping (0 or 65535)
                if dac_nxt not in (0, 65535) and dac_curr not in (0, 65535):
                    print(f"Row {i} (Packet {packet}): DAC{ch} step size mismatch! Expected move of {abs(scaled_update)}, but DAC moved from {dac_curr} to {dac_nxt} (diff: {diff})")
                    errors += 1
                    
        # Verify the deduced signs match the Hadamard matrix
        # Note: Hadamard signs are occasionally fully inverted depending on the epoch_flip bit!
        valid_indices = [idx for idx, s in enumerate(actual_signs) if s is not None and s != 0]
        
        if len(valid_indices) == 8: # Only check if no channels wrapped
            match_normal = all(actual_signs[c] == expected_rom[c] for c in valid_indices)
            match_flipped = all(actual_signs[c] == -expected_rom[c] for c in valid_indices)
            
            if not match_normal and not match_flipped:
                print(f"Row {i} (Packet {packet}): Dither sign mismatch!")
                print(f"  Hadamard Row {h_row} Matrix: {expected_rom}")
                print(f"  Actual Hardware Dither Applied: {actual_signs}")
                errors += 1
                
    print("-" * 50)
    if errors == 0:
        print(f"SUCCESS: Verification passed! All {len(rows)-1} hardware update cycles match mathematically.")
    else:
        print(f"FAILED: Found {errors} anomalies in the telemetry stream.")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python verify_telemetry.py <path_to_csv_file>")
    else:
        verify_csv(sys.argv[1])
