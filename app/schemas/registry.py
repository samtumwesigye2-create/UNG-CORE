from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl

class ServiceRegistrationIn(BaseModel):
    service_key: str = Field(min_length=2, max_length=80, pattern=r"^[A-Z0-9][A-Z0-9_-]+$")
    display_name: str = Field(min_length=2, max_length=160)
    base_url: HttpUrl
    version: str = Field(default="unknown", max_length=64)
    capabilities: list[str] = Field(default_factory=list)
    health_path: str = Field(default="/health", max_length=128)
    enabled: bool = True

class ServiceRegistrationOut(BaseModel):
    service_key: str
    display_name: str
    base_url: str
    version: str
    capabilities: list[str]
    health_path: str
    enabled: bool
    registered_at: datetime
    updated_at: datetime

class ServiceDiscoveryOut(BaseModel):
    service_key: str
    base_url: str
    version: str
    capabilities: list[str]
