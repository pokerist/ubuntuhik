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
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

# Configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_EVENTS_PREFIX = os.getenv('SUPABASE_EVENTS_PREFIX')
SUPABASE_BEARER_TOKEN = os.getenv('SUPABASE_BEARER_TOKEN')
SUPABASE_API_KEY = os.getenv('SUPABASE_API_KEY')
HIKCENTRAL_BASE_URL = os.getenv('HIKCENTRAL_BASE_URL')
HIKCENTRAL_APP_KEY = os.getenv('HIKCENTRAL_APP_KEY')
HIKCENTRAL_APP_SECRET = os.getenv('HIKCENTRAL_APP_SECRET')
HIKCENTRAL_ORG_INDEX_CODE = os.getenv('HIKCENTRAL_ORG_INDEX_CODE')
HIKCENTRAL_USER_ID = os.getenv('HIKCENTRAL_USER_ID', 'admin')
HIKCENTRAL_TIMEZONE_OFFSET = os.getenv('HIKCENTRAL_TIMEZONE_OFFSET', '+02:00')
DASHBOARD_ENABLED = os.getenv('DASHBOARD_ENABLED', 'True').lower() == 'true'
DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', '8080'))
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

    def update_worker_by_national_id(self, national_id: str, updates: Dict) -> bool:
        for worker in self.data['workers']:
            if worker.get('nationalIdNumber') == national_id:
                worker.update(updates)
                self.save()
                return True
        return False
    
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
        self.user_id = HIKCENTRAL_USER_ID
        self.tz_offset = HIKCENTRAL_TIMEZONE_OFFSET
        if not self.org_index_code:
            resolved = self._resolve_org_index_code()
            if resolved:
                self.org_index_code = resolved
    
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
            'X-Ca-Signature': signature,
            'userId': self.user_id
        }
        
        # Include Content-MD5 header when body is present so server can validate it
        if content_md5:
            headers['Content-MD5'] = content_md5
        
        return headers
    
    def _resolve_org_index_code(self) -> Optional[str]:
        try:
            data = {"pageNo": 1, "pageSize": 1}
            result = self._make_request('/api/resource/v1/org/brief/list', data)
            if result.get('code') == '0':
                items = result.get('data', {}).get('list', [])
                if items:
                    return items[0].get('indexCode')
        except Exception:
            pass
        return None

    def _format_time(self, date_str: str, start: bool) -> str:
        try:
            if start:
                return f"{date_str}T00:00:00{self.tz_offset}"
            else:
                return f"{date_str}T23:59:59{self.tz_offset}"
        except Exception:
            return f"2025-01-01T00:00:00{self.tz_offset}" if start else f"2035-12-31T23:59:59{self.tz_offset}"
    
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
        begin_date = worker.get('validFrom', '2025-01-01')
        end_date = worker.get('validTo', '2035-12-31')
        data = {
            "personCode": worker['nationalIdNumber'],
            "personFamilyName": family_name,
            "personGivenName": given_name,
            "gender": 1,
            "orgIndexCode": org_code,
            "phoneNo": worker.get('delegatedUserMobile', ''),
            "email": worker.get('delegatedUserEmail', ''),
            "faces": [
                {
                    "faceData": face_base64
                }
            ],
            "fingerPrint": [],
            "cards": [],
            "beginTime": self._format_time(begin_date, True),
            "endTime": self._format_time(end_date, False),
            "residentRoomNo": 1,
            "residentFloorNo": 1
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

    def update_person(self, person_id: str, worker: Dict, begin_date: str, end_date: str) -> bool:
        org_code = self.org_index_code or "1"
        data = {
            "personId": person_id,
            "personCode": worker['nationalIdNumber'],
            "personFamilyName": worker['fullName'].strip().split()[-1] if worker['fullName'].strip().split() else "",
            "personGivenName": " ".join(worker['fullName'].strip().split()[:-1]) if len(worker['fullName'].strip().split()) > 1 else "",
            "orgIndexCode": org_code,
            "gender": 1,
            "phoneNo": worker.get('delegatedUserMobile', ''),
            "remark": "",
            "email": worker.get('delegatedUserEmail', ''),
            "cards": [],
            "beginTime": self._format_time(begin_date, True),
            "endTime": self._format_time(end_date, False),
            "residentRoomNo": 1,
            "residentFloorNo": 1
        }
        result = self._make_request('/api/resource/v1/person/single/update', data)
        return result.get('code') == '0'

    def delete_person_full(self, person_id: str) -> bool:
        data = {"personId": person_id}
        result = self._make_request('/api/resource/v1/person/single/delete', data)
        return result.get('code') == '0'


class SupabaseAPI:
    """Supabase API Client"""
    
    def __init__(self):
        self.base_url = SUPABASE_URL
        self.bearer_token = SUPABASE_BEARER_TOKEN
        self.api_key = SUPABASE_API_KEY
        self.events_prefix = SUPABASE_EVENTS_PREFIX
    
    def _get_headers(self) -> Dict[str, str]:
        h = {'Content-Type': 'application/json'}
        if self.api_key:
            h['X-API-Key'] = self.api_key
        if self.bearer_token:
            h['Authorization'] = f'Bearer {self.bearer_token}'
        return h
    
    def get_pending_events(self, limit: int = 100, type_filter: Optional[str] = None) -> Dict:
        if not self.events_prefix:
            print('[Supabase] Missing SUPABASE_EVENTS_PREFIX')
            return {'success': False, 'events': []}
        url = f"{self.base_url}/{self.events_prefix}/admin/events/pending"
        params = {}
        if limit:
            params['limit'] = limit
        if type_filter:
            params['type'] = type_filter
        print(f"[Supabase] Fetching pending events...")
        try:
            response = requests.get(url, headers=self._get_headers(), params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            if data.get('success'):
                print(f"[Supabase] Received {data.get('count', 0)} new events, pending left: {data.get('totalPending', 0)}")
            else:
                print(f"[Supabase] Error: {data}")
            return data
        except Exception as e:
            print(f"[Supabase] Events request failed: {e}")
            return {'success': False, 'events': []}
    
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
        self.last_sync_started = None
        self.last_sync_finished = None
        self.last_sync_error = None
    
    def _map_event_worker(self, ew: Dict) -> Dict:
        return {
            'id': ew.get('workerId'),
            'nationalIdNumber': ew.get('nationalIdNumber'),
            'fullName': ew.get('fullName'),
            'status': ew.get('status', 'pending'),
            'blocked': bool(ew.get('blocked', False)),
            'blockedReason': ew.get('blockedReason'),
            'facePhoto': ew.get('facePhoto'),
            'nationalIdImage': ew.get('nationalIdImage'),
            'unitNumber': (ew.get('unit') or {}).get('unitNumber'),
            'delegatedUserMobile': (ew.get('delegatedUser') or {}).get('mobileNumber'),
            'delegatedUserEmail': (ew.get('delegatedUser') or {}).get('email'),
            'validFrom': None,
            'validTo': None
        }

    def handle_event(self, event: Dict):
        et = event.get('type')
        workers = event.get('workers', [])
        if et in ['worker.created', 'workers.bulk_created', 'worker.unblocked', 'unit.workers_unblocked']:
            for ew in workers:
                w = self._map_event_worker(ew)
                w['blocked'] = False
                self.process_worker(w)
        elif et in ['worker.blocked', 'unit.workers_blocked']:
            for ew in workers:
                w = self._map_event_worker(ew)
                w['blocked'] = True
                self.process_worker(w)
        elif et in ['worker.deleted', 'user.deleted_workers_deleted', 'user.expired_workers_deleted', 'worker.revoked']:
            for ew in workers:
                w = self._map_event_worker(ew)
                existing = self.db.get_worker_by_national_id(w.get('nationalIdNumber') or '')
                if existing and existing.get('hikcentral_id'):
                    self.hikcentral.delete_person_full(existing['hikcentral_id'])
                    self.db.update_worker_by_national_id(w['nationalIdNumber'], {
                        'blocked': True,
                        'hikcentral_deleted': True,
                        'updated_at': datetime.now().isoformat()
                    })
        else:
            pass
    
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
        
        existing_by_nat = self.db.get_worker_by_national_id(national_id)
        
        if blocked:
            if existing_by_nat:
                if existing_by_nat.get('hikcentral_deleted'):
                    self.db.update_worker_by_national_id(national_id, {
                        'blocked': True,
                        'blocked_at': datetime.now().isoformat()
                    })
                    self.supabase.update_worker_status(worker_id, 'blocked', external_id=existing_by_nat.get('hikcentral_id'))
                    return
                if existing_by_nat.get('hikcentral_id'):
                    print(f"[Worker] Blocked worker - deleting from HikCentral")
                    if self.hikcentral.delete_person_full(existing_by_nat['hikcentral_id']):
                        self.db.update_worker_by_national_id(national_id, {
                            'blocked': True,
                            'blocked_at': datetime.now().isoformat(),
                            'hikcentral_deleted': True
                        })
                        self.supabase.update_worker_status(worker_id, 'blocked', external_id=existing_by_nat['hikcentral_id'])
                    return
                self.db.update_worker_by_national_id(national_id, {
                    'blocked': True,
                    'blocked_at': datetime.now().isoformat()
                }) or self.db.add_worker({
                    'id': worker_id,
                    'nationalIdNumber': national_id,
                    'fullName': full_name,
                    'status': 'blocked',
                    'blocked': True,
                    'hikcentral_deleted': False,
                    'created_at': datetime.now().isoformat()
                })
                self.supabase.update_worker_status(worker_id, 'blocked')
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
        
        # Add or update in HikCentral
        print(f"[Worker] Adding to HikCentral...")
        if existing_by_nat and existing_by_nat.get('hikcentral_id'):
            existing_begin = existing_by_nat.get('validFrom', worker.get('validFrom', '2025-01-01'))
            existing_end = existing_by_nat.get('validTo', worker.get('validTo', '2035-12-31'))
            incoming_begin = worker.get('validFrom', existing_begin)
            incoming_end = worker.get('validTo', existing_end)
            merged_begin = min(existing_begin, incoming_begin)
            merged_end = max(existing_end, incoming_end)
            print(f"[Worker] Updating in HikCentral...")
            if self.hikcentral.update_person(existing_by_nat['hikcentral_id'], worker, merged_begin, merged_end):
                self.db.update_worker_by_national_id(national_id, {
                    'fullName': full_name,
                    'status': 'approved',
                    'blocked': False,
                    'hikcentral_deleted': False,
                    'face_path': str(face_path),
                    'id_card_path': str(id_card_path),
                    'validFrom': merged_begin,
                    'validTo': merged_end,
                    'updated_at': datetime.now().isoformat()
                })
                self.supabase.update_worker_status(worker_id, 'approved', external_id=existing_by_nat['hikcentral_id'])
                print(f"[Worker] ✓ Successfully updated")
            else:
                print(f"[Worker] ✗ Failed to update in HikCentral")
        else:
            person_id = self.hikcentral.add_person(worker, face_base64)
            if person_id:
                if self.hikcentral.add_to_privilege_group(person_id):
                    print(f"[Worker] Added to privilege group")
                worker_data = {
                    'id': worker_id,
                    'nationalIdNumber': national_id,
                    'fullName': full_name,
                    'hikcentral_id': person_id,
                    'status': 'approved',
                    'blocked': False,
                    'hikcentral_deleted': False,
                    'face_path': str(face_path),
                    'id_card_path': str(id_card_path),
                    'validFrom': worker.get('validFrom', '2025-01-01'),
                    'validTo': worker.get('validTo', '2035-12-31'),
                    'created_at': datetime.now().isoformat()
                }
                self.db.add_worker(worker_data)
                self.supabase.update_worker_status(worker_id, 'approved', external_id=person_id)
                print(f"[Worker] ✓ Successfully processed")
            else:
                print(f"[Worker] ✗ Failed to add to HikCentral")
    
    def sync(self):
        """Main sync function"""
        print(f"\n{'#'*60}")
        self.last_sync_started = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"# Sync started at {self.last_sync_started}")
        print(f"{'#'*60}\n")
        
        try:
            data = self.supabase.get_pending_events(limit=100)
            events = data.get('events', []) if isinstance(data, dict) else []
            if not events:
                print("[Sync] No events to process")
                return
            for ev in events:
                try:
                    self.handle_event(ev)
                except Exception as e:
                    print(f"[Error] Failed to process event: {e}")
                    import traceback
                    traceback.print_exc()
            
            self.last_sync_finished = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.last_sync_error = None
            print(f"\n[Sync] ✓ Sync completed at {self.last_sync_finished}")
            
        except Exception as e:
            self.last_sync_error = str(e)
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
    if not SUPABASE_URL or not HIKCENTRAL_BASE_URL:
        print("[Error] Missing SUPABASE_URL or HIKCENTRAL_BASE_URL in .env")
        return
    if not (SUPABASE_API_KEY or SUPABASE_BEARER_TOKEN):
        print("[Error] Missing authentication: set SUPABASE_API_KEY or SUPABASE_BEARER_TOKEN in .env")
        return
    
    print(f"[Config] Supabase URL: {SUPABASE_URL[:50]}...")
    print(f"[Config] HikCentral URL: {HIKCENTRAL_BASE_URL}")
    print(f"[Config] Sync Interval: {SYNC_INTERVAL} seconds")
    print(f"[Config] SSL Verification: {VERIFY_SSL}")
    print()
    
    # Initialize sync controller
    controller = SyncController()
    dashboard_context = {
        'controller': controller,
        'db': controller.db
    }
    
    # Run first sync immediately
    print("[System] Running initial sync...")
    controller.sync()
    
    # Schedule periodic syncs
    schedule.every(SYNC_INTERVAL).seconds.do(controller.sync)
    
    print(f"\n[System] Sync scheduler started (every {SYNC_INTERVAL} seconds)")
    print("[System] Press Ctrl+C to stop\n")
    if DASHBOARD_ENABLED:
        class DashboardHandler(BaseHTTPRequestHandler):
            def _send_json(self, obj):
                data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def _send_html(self, html):
                data = html.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def do_GET(self):
                if self.path == '/' or self.path.startswith('/index'):
                    html = (
                        "<!doctype html><html><head><meta charset='utf-8'>"
                        "<title>HydePark Sync Dashboard</title>"
                        "<style>body{font-family:sans-serif;margin:20px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:8px}th{background:#f5f5f5}code{background:#eee;padding:2px 4px;border-radius:3px}</style>"
                        "</head><body>"
                        "<h2>HydePark Sync Dashboard</h2>"
                        "<div id='status'></div>"
                        "<h3>Workers</h3>"
                        "<table id='workers'><thead><tr><th>ID</th><th>National ID</th><th>Name</th><th>HikCentral ID</th><th>Status</th><th>Blocked</th><th>Valid From</th><th>Valid To</th></tr></thead><tbody></tbody></table>"
                        "<script>async function load(){const s=await fetch('/api/status').then(r=>r.json());document.getElementById('status').innerHTML=`<p><b>Last Sync:</b> start: <code>${s.last_sync_started||'-'}</code>, finish: <code>${s.last_sync_finished||'-'}</code>, error: <code>${s.last_sync_error||'-'}</code></p>`;const w=await fetch('/api/workers').then(r=>r.json());const tb=document.querySelector('#workers tbody');tb.innerHTML='';w.forEach(x=>{const tr=document.createElement('tr');tr.innerHTML=`<td>${x.id||''}</td><td>${x.nationalIdNumber||''}</td><td>${x.fullName||''}</td><td>${x.hikcentral_id||''}</td><td>${x.status||''}</td><td>${x.blocked?'Yes':'No'}</td><td>${x.validFrom||''}</td><td>${x.validTo||''}</td>`;tb.appendChild(tr);});}load();setInterval(load,10000);</script>"
                        "</body></html>"
                    )
                    return self._send_html(html)
                if self.path.startswith('/api/workers'):
                    data = dashboard_context['db'].data.get('workers', [])
                    return self._send_json(data)
                if self.path.startswith('/api/status'):
                    c = dashboard_context['controller']
                    return self._send_json({
                        'last_sync_started': c.last_sync_started,
                        'last_sync_finished': c.last_sync_finished,
                        'last_sync_error': c.last_sync_error,
                        'count_workers': len(dashboard_context['db'].data.get('workers', []))
                    })
                self.send_response(404)
                self.end_headers()
        httpd = HTTPServer(('0.0.0.0', DASHBOARD_PORT), DashboardHandler)
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        print(f"[Dashboard] Running on port {DASHBOARD_PORT}")
    
    # Run scheduler
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[System] Shutting down...")


if __name__ == '__main__':
    main()
