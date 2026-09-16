import datetime
import json
import os
import random
import re
import sys
import time
from enum import Enum

import requests

USER = ""
PASSWORD = ""
OUTPUT_FILE = "rae_word_ids.csv"
CHECKPOINT_FILE = "checkpoint.json"
WORDS_PER_CHECKPOINT = 100

class Mode(Enum):
    PREFIX  = "31"
    SUFIX   = "32"
    INFIX   = "33"

class LemarioExtractor:
    def __init__(self, alphabet, mode=Mode.PREFIX, initialSearch=None, stopSearch=None, checkpoint_mgr=None):
        self.__alphabet = alphabet
        self.__mode = mode
        # FIX: Keep alphabet[0] so it searches "a" instead of the whole alphabet string!
        self.__search = initialSearch if initialSearch is not None else alphabet[0]
        self.__stop = stopSearch
        self.__infixes = {}
        for char in self.__alphabet:
            self.__infixes.update({char: self.__alphabet})
        self.__maxResults = LemarioExtractor.getMaxResults()
        self.checkpoint_mgr = checkpoint_mgr

    def set_current_search(self, search_term):
        self.__search = search_term

    def __longerSearch(self):
        self.__search += self.__alphabet[0]

    def __nextSearch(self):
        if len(self.__search) == 0:
            return
        
        current_letter = self.__search[-1]
        idx = self.__alphabet.find(current_letter)
        
        if idx != -1 and idx < len(self.__alphabet) - 1:
            next_letter = self.__alphabet[idx + 1]
            self.__search = self.__search[:-1] + next_letter
        else:
            self.__search = self.__search[:-1]
            self.__nextSearch()

    @staticmethod
    def __getRaeLemasApp(search, mode):
        url = "https://dle.rae.es/data/search"
        payload = {'w': search, 'm': mode.value}
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Connection': 'keep-alive'
        }
        
        numErrors = 0
        while True:
            try:
                result = requests.get(url, params=payload, auth=(USER, PASSWORD), headers=headers, timeout=15)
                
                if result.status_code != 200:
                    print(f"Server returned HTTP {result.status_code} for '{search}'. Details: {result.text[:150]}", file=sys.stderr)
                    raise ValueError(f"HTTP Status {result.status_code}")
                
                json_data = result.json()
                return json_data.get('res', [])
            except Exception as e:
                numErrors += 1
                print(f"Error calling token '{search}' (Attempt {numErrors}/10): {e}", file=sys.stderr, flush=True)
                if numErrors < 10:
                    time.sleep(numErrors * (1.0 + random.random()))
                else:
                    print("Critical threshold failed. Exiting script gracefully.", file=sys.stderr, flush=True)
                    return None

    def __printRaeLemas(self, lemas, file_handle):
        for lema in lemas:
            clean_lema = lema['lema'].replace('"', '""')
            print(f'"{clean_lema}","{lema["id"]}"', file=file_handle, flush=True)

    def getLemario(self, file_handle, phase_name):
        while len(self.__search) > 0 and self.__search != self.__stop:
            jsonResults = LemarioExtractor.__getRaeLemasApp(self.__search, self.__mode)
            
            if jsonResults is None:
                if self.checkpoint_mgr:
                    self.checkpoint_mgr.save(phase_name, self.__search)
                sys.exit("Script aborted due to connectivity errors. Checkpoint saved.")

            lemas = []
            p = re.compile(r'(?:<i>)?([^<.]*)(?:</i>)?(?:<sup>.*</sup>)?')

            for res in jsonResults:
                header_text = res.get('header', '')
                m = p.match(header_text)
                lema = m.group(1).strip() if m else header_text
                lemas.append({"lema": lema, "id": res['id']})

            print(f"[{phase_name}] Checking prefix: '{self.__search}' -> Found {len(lemas)} words", flush=True)
            self.__printRaeLemas(lemas, file_handle)
            
            # Periodic Checkpoint Trigger tracking word counts
            if self.checkpoint_mgr:
                self.checkpoint_mgr.add_count(len(lemas), phase_name, self.__search)
            
            if len(lemas) >= self.__maxResults:
                self.__longerSearch()
            else:
                self.__nextSearch()

    @staticmethod
    def getMaxResults():
        try:
            res = LemarioExtractor.__getRaeLemasApp("a", Mode.PREFIX)
            return len(res) if res else 20
        except:
            return 20 


class CheckpointTracker:
    def __init__(self):
        self.counter = 0
        self.total_saved = 0

    def add_count(self, count, phase, search):
        self.counter += count
        self.total_saved += count
        if self.counter >= WORDS_PER_CHECKPOINT:
            self.save(phase, search)
            self.counter = 0

    def save(self, phase, search):
        data = {
            "phase": phase,
            "search": search,
            "total_saved": self.total_saved,
            "timestamp": datetime.datetime.now().isoformat()
        }
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        print(f"\n>>> [CHECKPOINT AUTOMATIC SAVE] Phase: '{phase}' | Resuming prefix: '{search}' | Total Word IDs captured: {self.total_saved}\n", flush=True)


def main():
    print(f"STARTING FULL DICTIONARY MAPPING: {datetime.datetime.now().isoformat()}", flush=True)
    
    checkpoint_mgr = CheckpointTracker()
    saved_state = None
    
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as cp_file:
                saved_state = json.load(cp_file)
                checkpoint_mgr.total_saved = saved_state.get("total_saved", 0)
                print(f"--> Found checkpoint file! Recovering and resuming Phase: '{saved_state['phase']}' at Branch: '{saved_state['search']}'")
        except Exception as e:
            print(f"Could not read checkpoint file, starting fresh: {e}")

    file_mode = "a" if saved_state else "w"
    
    # Complete original execution profiles loop sequence
    phases = [
        {"name": "lowercase", "alphabet": "aábcdeéfghiíjklmnñoópqrstuúüvwxyz-", "mode": Mode.PREFIX, "initial": None},
        {"name": "capitals", "alphabet": "AÁBCDEÉFGHIÍJKLMNÑOÓPQRSTUÚÜVWXYZ", "mode": Mode.INFIX, "initial": None},
        {"name": "spaces", "alphabet": "aábcdeéfghiíjklmnñoópqrstuúüvwxyz", "mode": Mode.INFIX, "initial": "a a"},
        {"name": "rare", "alphabet": "àèìòùâêîôûäëïö‒", "mode": Mode.INFIX, "initial": None}
    ]

    skip_completed_phases = True if saved_state else False
    target_phase = saved_state["phase"] if saved_state else None
    target_search = saved_state["search"] if saved_state else None

    with open(OUTPUT_FILE, file_mode, encoding="utf-8") as f:
        if file_mode == "w":
            f.write('"Word","RAE_ID"\n')

        for phase in phases:
            if skip_completed_phases:
                if phase["name"] != target_phase:
                    continue
                else:
                    skip_completed_phases = False
            
            print(f"\n--- Starting extraction cycle phase: [{phase['name'].upper()}] ---", flush=True)
            
            extractor = LemarioExtractor(
                alphabet=phase["alphabet"], 
                mode=phase["mode"], 
                initialSearch=phase["initial"], 
                checkpoint_mgr=checkpoint_mgr
            )
            
            if target_search and phase["name"] == target_phase:
                extractor.set_current_search(target_search)
                target_search = None # Reset so later phases use defaults
                
            extractor.getLemario(f, phase["name"])
            
            # Save progress clean checkpoint whenever a full profile ends
            checkpoint_mgr.save(phase["name"], "")

    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        
    print(f"COMPLETED! Output saved to {OUTPUT_FILE}", flush=True)

if __name__ == "__main__":
    main()