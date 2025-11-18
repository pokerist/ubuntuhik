#!/usr/bin/env python3
"""
HydePark Local Server - Simple Sync System
Syncs workers from Supabase API to HikCentral (No Face Recognition)
"""

import os
import json
import time
import base64
import requests
import schedule
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

# Configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_BEARER_TOKEN = os.getenv('SUPABASE_BEARER_TOKEN')
SUPABASE_API_KEY = os.getenv('SUPABASE_API_KEY')
HIKCENTRAL_BASE_URL = os.getenv('HIKCENTRAL_BASE_URL')
HIKCENTRAL_APP_KEY = os.getenv('HIKCENTRAL_APP_KEY')
HIKCENTRAL_APP_SECRET = os.getenv('HIKCENTRAL_APP_SECRET')
HIKCENTRAL_PRIVILEGE_GROUP_ID = os.getenv('HIKCENTRAL_PRIVILEGE_GROUP_ID', '3')
SYNC_INTERVAL = int(os.getenv('SYNC_INTERVAL_SECONDS', '60'))
VERIFY_SSL = os.getenv('VERIFY_SSL', 'False').lower() == 'true'

# Directories
BASE_DIR = Path(__file__).parent
IMAGES_DIR = BASE_DIR / 'images'
ID_CARDS_DIR = IMAGES_DIR / 'id_cards'
FACES_DIR = IMAGES_DIR / 'faces'
DATA_FILE = BASE_DIR / 'workers_data.json'

# Create directories
IMAGES_DIR.mkdir(exist_ok=True)
ID_CARDS_DIR.mkdir(exist_ok=True)
FACES_DIR.mkdir(exist_ok=True)


class WorkersDatabase:
    """Simple JSON-based database for workers"""
    
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.data = self._load()
    
    def _load(self) -> Dict:
        if self.file_path.exists():
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'workers': []}
    
    def save(self):
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def add_worker(self, worker_data: Dict):
        self.data['workers'].append(worker_data)
        self.save()
    
    def update_worker(self, worker_id: str, updates: Dict):
        for worker in self.data['workers']:
            if worker['id'] == worker_id:
                worker.update(updates)
                self.save()
                return True
        return False
    
    def get_worker_by_id(self, worker_id: str) -> Optional[Dict]:
        for worker in self.data['workers']:
            if worker['id'] == worker_id:
                return worker
        return None
    
    def get_worker_by_national_id(self, national_id: str) -> Optional[Dict]:
        for worker in self.data['workers']:
            if worker.get('nationalIdNumber') == national_id:
                return worker
        return None
    
    def is_worker_processed(self, worker_id: str) -> bool:
        """Check if worker was already processed"""
        return self.get_worker_by_id(worker_id) is not None


class HikCentralAPI:
    """HikCentral API Client"""
    
    def __init__(self):
        self.base_url = HIKCENTRAL_BASE_URL
        self.app_key = HIKCENTRAL_APP_KEY
        self.app_secret = HIKCENTRAL_APP_SECRET
        self.privilege_group_id = HIKCENTRAL_PRIVILEGE_GROUP_ID
    
    def _get_headers(self) -> Dict[str, str]:
        """Generate headers with AK/SK authentication"""
        return {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Ca-Key': self.app_key
        }
    
    def _make_request(self, endpoint: str, data: Dict) -> Dict:
        """Make authenticated request to HikCentral"""
        url = f"{self.base_url}{endpoint}"
        
        # Add appSecret to request body
        data['appSecret'] = self.app_secret
        
        print(f"[HikCentral] POST {endpoint}")
        
        try:
            response = requests.post(
                url,
                json=data,
                headers=self._get_headers(),
                verify=VERIFY_SSL,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get('code') == '0':
                print(f"[HikCentral] Success: {result.get('msg')}")
                return result
            else:
                print(f"[HikCentral] Error: {result}")
                return result
                
        except Exception as e:
            print(f"[HikCentral] Request failed: {e}")
            return {'code': '-1', 'msg': str(e)}
    
    def add_person(self, worker: Dict, face_base64: str) -> Optional[str]:
        """Add person to HikCentral"""
        # Split name properly
        name_parts = worker['fullName'].strip().split()
        family_name = name_parts[-1] if name_parts else "Unknown"
        given_name = " ".join(name_parts[:-1]) if len(name_parts) > 1 else "Unknown"
        
        data = {
            "personCode": worker['nationalIdNumber'],
            "personFamilyName": family_name,
            "personGivenName": given_name,
            "gender": 1,
            "orgIndexCode": "1",
            "remark": f"Added via HydePark Sync - {worker.get('unitNumber', 'N/A')}",
            "phoneNo": worker.get('delegatedUserMobile', ''),
            "email": worker.get('delegatedUserEmail', ''),
            "faces": [
                {
                    "faceData": face_base64
                }
            ],
            "fingerPrint": [],
            "cards": [],
            "beginTime": worker.get('validFrom', '2025-01-01') + 'T00:00:00+02:00',
            "endTime": worker.get('validTo', '2035-12-31') + 'T23:59:59+02:00',
            "residentRoomNo": 0,
            "residentFloorNo": 0
        }
        
        result = self._make_request('/api/resource/v1/person/single/add', data)
        
        if result.get('code') == '0':
            person_id = result.get('data')
            print(f"[HikCentral] Person added with ID: {person_id}")
            return person_id
        
        return None
    
    def add_to_privilege_group(self, person_id: str) -> bool:
        """Add person to privilege group (Blue Collars)"""
        data = {
            "privilegeGroupId": self.privilege_group_id,
            "type": 1,
            "list": [
                {
                    "id": person_id
                }
            ]
        }
        
        result = self._make_request('/api/acs/v1/privilege/group/single/addPersons', data)
        return result.get('code') == '0'
    
    def delete_person(self, person_id: str) -> bool:
        """Remove person from HikCentral privilege group"""
        remove_data = {
            "privilegeGroupId": self.privilege_group_id,
            "type": 1,
            "list": [
                {
                    "id": person_id
                }
            ]
        }
        
        self._make_request('/api/acs/v1/privilege/group/single/deletePersons', remove_data)
        print(f"[HikCentral] Person {person_id} removed from privilege group")
        return True


class SupabaseAPI:
    """Supabase API Client"""
    
    def __init__(self):
        self.base_url = SUPABASE_URL
        self.bearer_token = SUPABASE_BEARER_TOKEN
        self.api_key = SUPABASE_API_KEY
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self.bearer_token}',
            'X-API-Key': self.api_key,
            'Content-Type': 'application/json'
        }
    
    def get_workers(self) -> List[Dict]:
        """Fetch workers from Supabase API"""
        url = f"{self.base_url}/admin/workers/all-data"
        
        print(f"[Supabase] Fetching workers...")
        
        try:
            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('success'):
                workers = data.get('workers', [])
                print(f"[Supabase] Fetched {len(workers)} workers")
                print(f"  - New: {data.get('newWorkers', 0)}")
                print(f"  - Pending: {data.get('pendingWorkers', 0)}")
                print(f"  - Blocked: {data.get('blockedWorkers', 0)}")
                return workers
            
            print(f"[Supabase] Error: {data}")
            return []
            
        except Exception as e:
            print(f"[Supabase] Request failed: {e}")
            return []
    
    def update_worker_status(self, worker_id: str, status: str, external_id: Optional[str] = None, blocked_reason: Optional[str] = None) -> bool:
        """Update worker status in Supabase"""
        url = f"{self.base_url}/admin/workers/update-status"
        
        data = {
            'workerId': worker_id,
            'status': status
        }
        
        if external_id:
            data['externalId'] = external_id
        
        if blocked_reason:
            data['blockedReason'] = blocked_reason
        
        print(f"[Supabase] Updating worker {worker_id} to {status}")
        
        try:
            response = requests.post(
                url,
                json=data,
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get('success'):
                print(f"[Supabase] Status updated successfully")
                return True
            
            print(f"[Supabase] Update failed: {result}")
            return False
            
        except Exception as e:
            print(f"[Supabase] Update failed: {e}")
            return False


class ImageDownloader:
    """Simple image downloader"""
    
    @staticmethod
    def download_image(url: str, save_path: Path) -> bool:
        """Download image from URL"""
        try:
            print(f"[Image] Downloading from {url[:50]}...")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            with open(save_path, 'wb') as f:
                f.write(response.content)
            
            print(f"[Image] Saved to {save_path}")
            return True
            
        except Exception as e:
            print(f"[Image] Download failed: {e}")
            return False
    
    @staticmethod
    def image_to_base64(image_path: Path) -> str:
        """Convert image to base64"""
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')


class SyncController:
    """Main synchronization controller"""
    
    def __init__(self):
        self.db = WorkersDatabase(DATA_FILE)
        self.supabase = SupabaseAPI()
        self.hikcentral = HikCentralAPI()
        self.downloader = ImageDownloader()
    
    def process_worker(self, worker: Dict):
        """Process a single worker"""
        worker_id = worker['id']
        national_id = worker['nationalIdNumber']
        full_name = worker['fullName']
        status = worker['status']
        blocked = worker['blocked']
        
        print(f"\n{'='*60}")
        print(f"[Worker] Processing: {full_name} ({national_id})")
        print(f"[Worker] Status: {status}, Blocked: {blocked}")
        print(f"{'='*60}")
        
        # Check if already processed
        if self.db.is_worker_processed(worker_id):
            print(f"[Worker] Already processed - skipping")
            return
        
        # Handle blocked workers
        if blocked:
            existing = self.db.get_worker_by_national_id(national_id)
            if existing and existing.get('hikcentral_id'):
                print(f"[Worker] Blocked worker - removing from HikCentral")
                self.hikcentral.delete_person(existing['hikcentral_id'])
                self.db.update_worker(worker_id, {
                    'blocked': True,
                    'blocked_at': datetime.now().isoformat()
                })
            return
        
        # Download images
        face_path = FACES_DIR / f"{worker_id}_face.jpg"
        id_card_path = ID_CARDS_DIR / f"{worker_id}_id.jpg"
        
        if not self.downloader.download_image(worker['facePhoto'], face_path):
            print(f"[Worker] Failed to download face photo - skipping")
            return
        
        if not self.downloader.download_image(worker['nationalIdImage'], id_card_path):
            print(f"[Worker] Failed to download ID card - skipping")
            return
        
        # Convert face image to base64
        face_base64 = self.downloader.image_to_base64(face_path)
        
        # Add to HikCentral
        print(f"[Worker] Adding to HikCentral...")
        person_id = self.hikcentral.add_person(worker, face_base64)
        
        if person_id:
            # Add to privilege group
            if self.hikcentral.add_to_privilege_group(person_id):
                print(f"[Worker] Added to privilege group")
            
            # Save to local database
            worker_data = {
                'id': worker_id,
                'nationalIdNumber': national_id,
                'fullName': full_name,
                'hikcentral_id': person_id,
                'status': 'approved',
                'blocked': False,
                'face_path': str(face_path),
                'id_card_path': str(id_card_path),
                'created_at': datetime.now().isoformat()
            }
            
            self.db.add_worker(worker_data)
            
            # Update online status
            self.supabase.update_worker_status(
                worker_id,
                'approved',
                external_id=person_id
            )
            
            print(f"[Worker] ✓ Successfully processed")
        else:
            print(f"[Worker] ✗ Failed to add to HikCentral")
    
    def sync(self):
        """Main sync function"""
        print(f"\n{'#'*60}")
        print(f"# Sync started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'#'*60}\n")
        
        try:
            # Fetch workers from Supabase
            workers = self.supabase.get_workers()
            
            if not workers:
                print("[Sync] No workers to process")
                return
            
            # Process each worker
            for worker in workers:
                try:
                    self.process_worker(worker)
                except Exception as e:
                    print(f"[Error] Failed to process worker: {e}")
                    import traceback
                    traceback.print_exc()
            
            print(f"\n[Sync] ✓ Sync completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
        except Exception as e:
            print(f"\n[Sync] ✗ Sync failed: {e}")
            import traceback
            traceback.print_exc()


def main():
    """Main entry point"""
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║         HydePark Local Server - Simple Sync                ║
    ║              Auto-Add Workers to HikCentral                ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    # Verify configuration
    if not all([SUPABASE_URL, SUPABASE_BEARER_TOKEN, HIKCENTRAL_BASE_URL]):
        print("[Error] Missing configuration! Please check your .env file")
        return
    
    print(f"[Config] Supabase URL: {SUPABASE_URL[:50]}...")
    print(f"[Config] HikCentral URL: {HIKCENTRAL_BASE_URL}")
    print(f"[Config] Sync Interval: {SYNC_INTERVAL} seconds")
    print(f"[Config] SSL Verification: {VERIFY_SSL}")
    print()
    
    # Initialize sync controller
    controller = SyncController()
    
    # Run first sync immediately
    print("[System] Running initial sync...")
    controller.sync()
    
    # Schedule periodic syncs
    schedule.every(SYNC_INTERVAL).seconds.do(controller.sync)
    
    print(f"\n[System] Sync scheduler started (every {SYNC_INTERVAL} seconds)")
    print("[System] Press Ctrl+C to stop\n")
    
    # Run scheduler
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[System] Shutting down...")


if __name__ == '__main__':
    main()
