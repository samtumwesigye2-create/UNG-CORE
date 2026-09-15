from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

def now(): return datetime.now(timezone.utc)
def uid(): return str(uuid4())

class JobRecord(Base):
    __tablename__="job_registry"
    job_id: Mapped[str]=mapped_column(String(64),primary_key=True,default=uid)
    owner: Mapped[str]=mapped_column(String(160),index=True); system_key: Mapped[str]=mapped_column(String(120),index=True)
    job_type: Mapped[str]=mapped_column(String(100),index=True); state: Mapped[str]=mapped_column(String(24),default="queued",index=True)
    progress: Mapped[int]=mapped_column(Integer,default=0); resource_usage_json: Mapped[str]=mapped_column(Text,default="{}")
    failure: Mapped[str|None]=mapped_column(Text,nullable=True); scheduler_job_id: Mapped[str|None]=mapped_column(String(64),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)

class ReportOutput(Base):
    __tablename__="report_spool"
    output_id: Mapped[str]=mapped_column(String(64),primary_key=True,default=uid); owner: Mapped[str]=mapped_column(String(160),index=True)
    system_key: Mapped[str]=mapped_column(String(120),index=True); report_type: Mapped[str]=mapped_column(String(100),index=True)
    state: Mapped[str]=mapped_column(String(24),default="queued",index=True); storage_ref: Mapped[str]=mapped_column(String(500)); metadata_json: Mapped[str]=mapped_column(Text,default="{}")
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)

class StorageReference(Base):
    __tablename__="storage_registry"
    storage_id: Mapped[str]=mapped_column(String(64),primary_key=True,default=uid); logical_name: Mapped[str]=mapped_column(String(200),unique=True,index=True)
    scheme: Mapped[str]=mapped_column(String(24),index=True); reference: Mapped[str]=mapped_column(String(500)); system_key: Mapped[str]=mapped_column(String(120),index=True)
    metadata_json: Mapped[str]=mapped_column(Text,default="{}"); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)

class CompatibilityContract(Base):
    __tablename__="compatibility_contracts"
    contract_id: Mapped[str]=mapped_column(String(64),primary_key=True,default=uid); system_key: Mapped[str]=mapped_column(String(120),index=True)
    component: Mapped[str]=mapped_column(String(160),index=True); current_version: Mapped[str]=mapped_column(String(40)); policy: Mapped[str]=mapped_column(String(24),default="major-stable")
    enabled: Mapped[bool]=mapped_column(Boolean,default=True); updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)

class OperationAudit(Base):
    __tablename__="operation_audit"
    audit_id: Mapped[str]=mapped_column(String(64),primary_key=True,default=uid); actor: Mapped[str]=mapped_column(String(160),index=True)
    action: Mapped[str]=mapped_column(String(100),index=True); resource_id: Mapped[str|None]=mapped_column(String(255),nullable=True,index=True)
    requested_state: Mapped[str|None]=mapped_column(String(40),nullable=True); previous_state: Mapped[str|None]=mapped_column(String(40),nullable=True); resulting_state: Mapped[str|None]=mapped_column(String(40),nullable=True)
    success: Mapped[bool]=mapped_column(Boolean,default=False); detail: Mapped[str|None]=mapped_column(Text,nullable=True); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
