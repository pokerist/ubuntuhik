#!/usr/bin/env python3
"""
HydePark Local Server - Simple Sync System
Syncs workers from Supabase API to HikCentral (No Face Recognition)
"""

import os
import json
import time
import base64
import hashlib
import hmac
import uuid
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
HIKCENTRAL_ORG_INDEX_CODE = os.getenv('HIKCENTRAL_ORG_INDEX_CODE')
HIKCENTRAL_PRIVILEGE_GROUP_ID = os.getenv('HIKCENTRAL_PRIVILEGE_GROUP_ID', '3')
SYNC_INTERVAL = int(os.getenv('SYNC_INTERVAL_SECONDS', '60'))
VERIFY_SSL = os.getenv('VERIFY_SSL', 'False').lower() == 'true'
HIKCENTRAL_DEBUG = os.getenv('HIKCENTRAL_DEBUG', 'False').lower() == 'true'
HIKCENTRAL_INCLUDE_PORT_IN_URI = os.getenv('HIKCENTRAL_INCLUDE_PORT_IN_URI', 'False').lower() == 'true'

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
    """HikCentral API Client with proper AK/SK authentication"""
    
    def __init__(self):
        self.base_url = HIKCENTRAL_BASE_URL
        self.app_key = HIKCENTRAL_APP_KEY
        self.app_secret = HIKCENTRAL_APP_SECRET
        self.privilege_group_id = HIKCENTRAL_PRIVILEGE_GROUP_ID
        self.org_index_code = HIKCENTRAL_ORG_INDEX_CODE
    
    def _calculate_signature(self, method: str, accept: str, content_type: str,
                             uri: str, body: str, timestamp: str, nonce: str) -> tuple:
        """Calculate signature for HikCentral API.

        Builds the string-to-sign per documentation. Order matters:
        - HTTP method
        - Accept
        - (optional) Content-MD5 if body exists
        - Content-Type
        - x-ca-key:{app_key}
        - x-ca-nonce:{nonce}
        - x-ca-timestamp:{timestamp}
        - request URI (path)
        """

        # Calculate Content-MD5 if body is present
        content_md5 = ""
        if body:
            md5_hash = hashlib.md5(body.encode('utf-8')).digest()
            content_md5 = base64.b64encode(md5_hash).decode('utf-8')

        # Build signature string according to documentation
        parts = [method, accept]
        if content_md5:
            parts.append(content_md5)
        parts.append(content_type)
        parts.append(f"x-ca-key:{self.app_key}")
        parts.append(f"x-ca-nonce:{nonce}")
        parts.append(f"x-ca-timestamp:{timestamp}")
        parts.append(uri)

        string_to_sign = "\n".join(parts)

        # Debug: show the string to sign (helpful when fixing signature issues)
        if HIKCENTRAL_DEBUG:
            print("[HikCentral] StringToSign:\n" + string_to_sign)


        # Calculate signature using HmacSHA256
        signature_bytes = hmac.new(
            self.app_secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha256
        ).digest()

        signature = base64.b64encode(signature_bytes).decode('utf-8')

        return signature, content_md5
    
    def _get_headers(self, endpoint: str, body: str) -> Dict[str, str]:
        """Generate headers with AK/SK authentication"""
        method = "POST"
        accept = "application/json"
        # Use full content-type including charset (HikCentral examples use this)
        content_type = "application/json;charset=UTF-8"
        timestamp = str(int(time.time() * 1000))

        # Generate a nonce (GUID) and include it in signature
        nonce = str(uuid.uuid4())

        # Build the URI used for signing. Depending on environment flag, include the
        # base_url's path and optionally its port in the URI string used for signature.
        from urllib.parse import urlparse
        parsed = urlparse(self.base_url)
        base_path = parsed.path.rstrip('/') if parsed.path else ''
        port = parsed.port

        if HIKCENTRAL_INCLUDE_PORT_IN_URI and port:
            # e.g. '/artemis:443/api/resource/v1/person/single/add'
            uri_for_sign = f"{base_path}:{port}{endpoint}"
        else:
            # e.g. '/artemis/api/resource/v1/person/single/add'
            uri_for_sign = f"{base_path}{endpoint}"

        # Calculate signature
        signature, content_md5 = self._calculate_signature(
            method, accept, content_type, uri_for_sign, body, timestamp, nonce
        )

        headers = {
            'Accept': accept,
            'Content-Type': content_type,
            'X-Ca-Key': self.app_key,
            'X-Ca-Nonce': nonce,
            'X-Ca-Timestamp': timestamp,
            'X-Ca-Signature-Headers': 'x-ca-key,x-ca-nonce,x-ca-timestamp',
            'X-Ca-Signature': signature
        }
        
        # Include Content-MD5 header when body is present so server can validate it
        if content_md5:
            headers['Content-MD5'] = content_md5
        
        return headers
    
    def _make_request(self, endpoint: str, data: Dict) -> Dict:
        """Make authenticated request to HikCentral"""
        url = f"{self.base_url}{endpoint}"
        # Convert data to JSON string using canonical separators to ensure consistent MD5
        body = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
        
        # Get headers with signature
        headers = self._get_headers(endpoint, body)

        print(f"[HikCentral] POST {endpoint}")
        if HIKCENTRAL_DEBUG:
            # Print headers and body for debugging parameter issues
            try:
                print('[HikCentral][DEBUG] Request headers:')
                for k, v in headers.items():
                    print(f"  {k}: {v}")
                print('[HikCentral][DEBUG] Request body:')
                print(body)
            except Exception as _:
                pass
        
        try:
            response = requests.post(
                url,
                data=body.encode('utf-8'),
                headers=headers,
                verify=VERIFY_SSL,
                timeout=30
            )
            response.raise_for_status()
            # Always show raw response when debugging
            if HIKCENTRAL_DEBUG:
                print(f"[HikCentral][DEBUG] Response status: {response.status_code}")
                print(f"[HikCentral][DEBUG] Response text: {response.text}")

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
        
        org_code = self.org_index_code or "1"
        data = {
            "personCode": worker['nationalIdNumber'],
            "personName": worker['fullName'],
            "personFamilyName": family_name,
            "personGivenName": given_name,
            "gender": 1,
            "orgIndexCode": org_code,
            "remark": f"Added via HydePark Sync - {worker.get('unitNumber', 'N/A')}",
            "phoneNo": worker.get('delegatedUserMobile', ''),
            "email": worker.get('delegatedUserEmail', ''),
            "beginTime": worker.get('validFrom', '2025-01-01') + 'T00:00:00+02:00',
            "endTime": worker.get('validTo', '2035-12-31') + 'T23:59:59+02:00'
        }
        
        result = self._make_request('/api/resource/v1/person/single/add', data)
        
        if result.get('code') == '0':
            person_id = result.get('data')
            print(f"[HikCentral] Person added with ID: {person_id}")
            return person_id
        else:
            try:
                print("[HikCentral] Add person failed with payload:")
                print(json.dumps(data, ensure_ascii=False))
            except Exception:
                pass
        
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
