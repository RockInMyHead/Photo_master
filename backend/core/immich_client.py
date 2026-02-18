# backend/core/immich_client.py
"""
Immich API клиент для кластеризации лиц
"""
from __future__ import annotations
import asyncio
import httpx
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass
import json

from core.insightface_engine import FaceRecord


@dataclass
class ImmichConfig:
    """Конфигурация для подключения к Immich"""
    url: str  # Базовый URL Immich сервера (например, http://localhost:2283)
    api_key: str  # API ключ для аутентификации
    library_id: Optional[str] = None  # ID библиотеки (опционально)


class ImmichClient:
    """Клиент для работы с Immich API"""
    
    def __init__(self, config: ImmichConfig):
        self.config = config
        self.base_url = config.url.rstrip('/')
        self.headers = {
            "x-api-key": config.api_key,
            "Content-Type": "application/json",
        }
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Получить или создать HTTP клиент"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.headers,
                timeout=60.0,
            )
        return self._client
    
    async def close(self):
        """Закрыть HTTP клиент"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def test_connection(self) -> bool:
        """Проверить подключение к Immich"""
        try:
            client = await self._get_client()
            response = await client.get("/api/server/ping")
            return response.status_code == 200
        except Exception as e:
            print(f"Immich connection test failed: {e}")
            return False
    
    def _mime_type(self, path: Path) -> str:
        """Определить MIME-тип по расширению"""
        ext = path.suffix.lower()
        mime = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp",
            ".bmp": "image/bmp", ".tif": "image/tiff", ".tiff": "image/tiff",
        }
        return mime.get(ext, "image/jpeg")

    async def upload_asset(self, image_path: Path) -> Optional[str]:
        """
        Загрузить фото в Immich и вернуть asset ID
        
        Returns:
            asset_id или None при ошибке
        """
        try:
            import httpx as httpx_lib
            from datetime import datetime

            stats = image_path.stat()
            mtime = stats.st_mtime
            data = {
                "deviceAssetId": f"{image_path}-{mtime}",
                "deviceId": "photo-master",
                "fileCreatedAt": datetime.fromtimestamp(mtime).isoformat(),
                "fileModifiedAt": datetime.fromtimestamp(mtime).isoformat(),
                "isFavorite": "false",
            }
            headers = {
                "Accept": "application/json",
                "x-api-key": self.config.api_key,
            }

            with open(image_path, "rb") as f:
                files = {"assetData": (image_path.name, f, self._mime_type(image_path))}

                async with httpx_lib.AsyncClient() as client:
                    response = await client.post(
                        f"{self.base_url}/api/assets",
                        files=files,
                        data=data,
                        headers=headers,
                        timeout=120.0,
                    )

                    if response.status_code in [200, 201]:
                        result = response.json()
                        return result.get("id") or result.get("assetId")
                    else:
                        print(f"Failed to upload {image_path}: {response.status_code} - {response.text}")
                        return None
        except Exception as e:
            print(f"Error uploading {image_path} to Immich: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def wait_for_face_detection(self, asset_id: str, max_wait: int = 300) -> bool:
        """
        Дождаться обработки лица для asset
        
        Args:
            asset_id: ID загруженного asset
            max_wait: Максимальное время ожидания в секундах
        
        Returns:
            True если обработка завершена
        """
        client = await self._get_client()
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < max_wait:
            try:
                # Проверяем статус asset
                response = await client.get(f"/api/assets/{asset_id}")
                if response.status_code == 200:
                    # Проверяем, есть ли лица (Immich v2: /api/faces?id=assetId)
                    faces_response = await client.get("/api/faces", params={"id": asset_id})
                    if faces_response.status_code == 200:
                        faces = faces_response.json()
                        if len(faces) > 0:
                            return True
                
                await asyncio.sleep(2)  # Ждем 2 секунды перед следующей проверкой
            except Exception as e:
                print(f"Error checking face detection for {asset_id}: {e}")
                await asyncio.sleep(2)
        
        return False
    
    async def get_asset_faces(self, asset_id: str) -> List[Dict]:
        """Получить лица на asset"""
        try:
            client = await self._get_client()
            response = await client.get("/api/faces", params={"id": asset_id})
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            print(f"Error getting faces for asset {asset_id}: {e}")
            return []
    
    async def get_persons(self) -> List[Dict]:
        """Получить все кластеры лиц (persons)"""
        try:
            client = await self._get_client()
            response = await client.get("/api/people")
            if response.status_code == 200:
                data = response.json()
                return data.get("people", [])
            return []
        except Exception as e:
            print(f"Error getting persons: {e}")
            return []
    
    async def get_person_assets(self, person_id: str) -> List[Dict]:
        """Получить все assets для конкретного person (кластера)"""
        try:
            client = await self._get_client()
            # Пробуем разные варианты API endpoints
            # Вариант 1: через search
            try:
                assets_response = await client.get(
                    "/api/search/person",
                    params={"personId": person_id}
                )
                if assets_response.status_code == 200:
                    data = assets_response.json()
                    if isinstance(data, list):
                        return data
                    return data.get("items", []) or data.get("assets", [])
            except:
                pass
            
            # Вариант 2: через person endpoint
            try:
                response = await client.get(f"/api/person/{person_id}")
                if response.status_code == 200:
                    person = response.json()
                    # Может быть вложенный список assets
                    if "assets" in person:
                        return person["assets"] if isinstance(person["assets"], list) else []
            except:
                pass
            
            return []
        except Exception as e:
            print(f"Error getting assets for person {person_id}: {e}")
            return []
    
    async def upload_and_wait_for_faces(
        self,
        images: List[Path],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> List[Path]:
        """
        Только загрузка в Immich и ожидание детекта лиц.
        Возвращает список путей к изображениям (для последующей локальной кластеризации).
        """
        if progress_callback:
            progress_callback(10, "Загрузка изображений в Immich")
        
        asset_map: Dict[str, str] = {}  # image_path -> asset_id
        uploaded = 0
        
        for img_path in images:
            asset_id = await self.upload_asset(img_path)
            if asset_id:
                asset_map[str(img_path)] = asset_id
                uploaded += 1
                if progress_callback:
                    pct = 10 + int(30 * uploaded / len(images))
                    progress_callback(pct, f"Загружено {uploaded}/{len(images)}")
        
        if uploaded == 0:
            raise Exception("Не удалось загрузить ни одного изображения в Immich")
        
        # Шаг 2: Ожидание детекта лиц (кластеризацию делаем локально для качества)
        if progress_callback:
            progress_callback(40, "Ожидание детекта лиц в Immich")
        
        processed = 0
        for img_path, asset_id in asset_map.items():
            if await self.wait_for_face_detection(asset_id, max_wait=60):
                processed += 1
                if progress_callback:
                    pct = 40 + int(20 * processed / len(asset_map))
                    progress_callback(pct, f"Обработано {processed}/{len(asset_map)}")
        
        # Возвращаем пути для локальной кластеризации (Immich не даёт embeddings)
        return [Path(p) for p in asset_map.keys()]
    
    async def cluster_images(
        self,
        images: List[Path],
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> Tuple[List[FaceRecord], List[int]]:
        """Устаревший метод — используйте upload_and_wait_for_faces + локальную кластеризацию."""
        # Для обратной совместимости: загрузка + возврат путей (pipeline сделает локальную кластеризацию)
        paths = await self.upload_and_wait_for_faces(images, progress_callback)
        # Возвращаем пустые — pipeline переопределит логику
        return [], []
