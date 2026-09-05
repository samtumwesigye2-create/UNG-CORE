from typing import Any

from pydantic import BaseModel, Field


class OrganizationIn(BaseModel):
    organization_key: str = Field(min_length=2, max_length=120)
    display_name: str = Field(min_length=2, max_length=255)
    organization_type: str = Field(default="agency", max_length=80)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class SystemIn(BaseModel):
    system_key: str = Field(min_length=2, max_length=120)
    display_name: str = Field(min_length=2, max_length=255)
    owner_organization_key: str = Field(min_length=2, max_length=120)
    lifecycle_status: str = "active"
    criticality: str = "standard"
    base_url: str | None = None
    enabled: bool = True
    capabilities: list[str] = Field(default_factory=list)


class DependencyIn(BaseModel):
    depends_on_system_key: str = Field(min_length=2, max_length=120)
    dependency_type: str = "runtime"
    required: bool = True


class ConfigurationIn(BaseModel):
    value: Any = None
    is_secret_reference: bool = False
