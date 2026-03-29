"""Observation Point Metadata Service - Round 20
Provides business logic for observation point metadata management and alert context generation.
"""
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class AlertContext:
    """Alert context enriched with observation point metadata"""
    alert_id: str
    alert_data: Dict[str, Any]
    observation_point: Optional[Dict[str, Any]]
    explanation: str
    collection_info: Optional[str]
    anomaly_explanation: Optional[str]


class ObservationPointService:
    """Observation Point Metadata Service
    
    Manages observation point metadata that defines:
    - How to collect a metric (collection_method)
    - How to represent a metric (representation, unit)
    - What constitutes an anomaly (anomaly_pattern, anomaly_condition)
    
    Provides alert context enrichment to improve alert explainability.
    """

    def __init__(self, repo: Optional[Any] = None):
        """Initialize service with optional repository
        
        Args:
            repo: Optional ObservationPointRepository instance.
                  If not provided, will be created on first use.
        """
        self._repo = repo

    def set_repo(self, repo: Any) -> None:
        """Set repository instance
        
        Args:
            repo: ObservationPointRepository instance
        """
        self._repo = repo

    # =========================================================================
    # Metadata Access
    # =========================================================================

    async def get_observation_point(self, resource_type: str, metric: str) -> Optional[Dict]:
        """Get observation point metadata by resource type and metric
        
        Args:
            resource_type: Resource type (e.g., OS.CPU, DB.Connection)
            metric: Metric name (e.g., usage_percent, active_count)
            
        Returns:
            Dictionary with observation point metadata, or None if not found
        """
        if self._repo is None:
            raise RuntimeError("ObservationPointRepository not initialized. Call set_repo() first.")
        
        op = await self._repo.get_observation_point_by_resource_metric(resource_type, metric)
        
        if op is None:
            return None
        
        return self._op_to_dict(op)

    async def list_observation_points(self, entity_type: str = None) -> List[Dict]:
        """List all observation points, optionally filtered by resource type
        
        Args:
            entity_type: Optional resource type filter (e.g., OS.CPU)
            
        Returns:
            List of observation point metadata dictionaries
        """
        if self._repo is None:
            raise RuntimeError("ObservationPointRepository not initialized. Call set_repo() first.")
        
        if entity_type:
            ops = await self._repo.list_observation_points_by_resource_type(entity_type)
        else:
            ops = await self._repo.list_observation_points()
        
        return [self._op_to_dict(op) for op in ops]

    async def add_observation_point(self, op_data: Dict) -> Any:
        """Add a new observation point
        
        Args:
            op_data: Dictionary with observation point data
            
        Returns:
            Created ObservationPoint object
        """
        if self._repo is None:
            raise RuntimeError("ObservationPointRepository not initialized. Call set_repo() first.")
        
        from src.knowledge.db.repositories.observation_point_repo import ObservationPoint
        
        op = ObservationPoint(
            id=op_data["id"],
            resource_type=op_data["resource_type"],
            metric_name=op_data["metric_name"],
            collection_method=op_data["collection_method"],
            representation=op_data["representation"],
            anomaly_pattern=op_data.get("anomaly_pattern"),
            anomaly_condition=op_data.get("anomaly_condition"),
            unit=op_data.get("unit"),
            severity=op_data.get("severity"),
            metadata=op_data.get("metadata", {}),
        )
        
        result = await self._repo.create_observation_point(op)
        return result

    # =========================================================================
    # Alert Context Generation
    # =========================================================================

    async def generate_alert_context(self, alert: Any) -> Dict[str, Any]:
        """Generate enriched alert context with observation point metadata
        
        This method enhances an alert with information about:
        - How the metric is collected
        - What the metric values represent
        - What anomaly pattern triggered this alert
        - Why this is considered an anomaly
        
        Args:
            alert: Alert object or dict with at least:
                - resource_type: Resource type (e.g., OS.CPU)
                - metric: Metric name (e.g., usage_percent)
                - alert_id: Alert identifier
                - message: Alert message
                
        Returns:
            Dictionary with:
                - alert: Original alert data
                - observation_point: Observation point metadata (or None)
                - explanation: Human-readable explanation
                - collection_info: How the metric is collected
                - anomaly_explanation: Why this is an anomaly
        """
        # Extract alert information
        if hasattr(alert, "resource_type"):
            resource_type = alert.resource_type
        elif isinstance(alert, dict):
            resource_type = alert.get("resource_type", "")
        else:
            resource_type = ""

        if hasattr(alert, "metric"):
            metric = alert.metric
        elif isinstance(alert, dict):
            metric = alert.get("metric", "")
        else:
            metric = ""

        # Get observation point metadata
        op_dict = await self.get_observation_point(resource_type, metric)

        # Build alert data dict
        if hasattr(alert, "to_dict"):
            alert_data = alert.to_dict()
        elif isinstance(alert, dict):
            alert_data = alert
        else:
            alert_data = {"alert_id": getattr(alert, "alert_id", "unknown")}

        # Build explanation
        explanation_parts = []

        if op_dict:
            # Explain the metric
            explanation_parts.append(
                f"指标「{resource_type}.{metric}」的采集方法为: {op_dict['collection_method']}"
            )
            explanation_parts.append(
                f"该指标表示: {op_dict['representation']}"
            )
            
            if op_dict.get("anomaly_pattern"):
                explanation_parts.append(
                    f"异常模式: {op_dict['anomaly_pattern']}"
                )
            
            if op_dict.get("anomaly_condition"):
                explanation_parts.append(
                    f"异常条件: {op_dict['anomaly_condition']}"
                )
        else:
            explanation_parts.append(
                f"未找到指标「{resource_type}.{metric}」的观察点元数据"
            )

        explanation = " | ".join(explanation_parts)

        # Collection info
        collection_info = op_dict["collection_method"] if op_dict else None

        # Anomaly explanation
        anomaly_explanation = None
        if op_dict:
            if hasattr(alert, "metric_value") and hasattr(alert, "threshold"):
                value = alert.metric_value
                threshold = alert.threshold
                anomaly_explanation = (
                    f"当前值 {value} {op_dict.get('unit', '')} "
                    f"超过阈值 {threshold} {op_dict.get('unit', '')}，"
                    f"符合异常模式「{op_dict.get('anomaly_pattern', 'N/A')}」"
                )
            elif op_dict.get("anomaly_pattern"):
                anomaly_explanation = (
                    f"该告警符合异常模式「{op_dict['anomaly_pattern']}」"
                )

        return {
            "alert": alert_data,
            "observation_point": op_dict,
            "explanation": explanation,
            "collection_info": collection_info,
            "anomaly_explanation": anomaly_explanation,
        }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _op_to_dict(self, op: Any) -> Dict:
        """Convert ObservationPoint to dictionary"""
        if hasattr(op, "to_dict"):
            return op.to_dict()
        return {
            "id": op.id,
            "resource_type": op.resource_type,
            "metric_name": op.metric_name,
            "collection_method": op.collection_method,
            "representation": op.representation,
            "anomaly_pattern": op.anomaly_pattern,
            "anomaly_condition": op.anomaly_condition,
            "unit": op.unit,
            "severity": op.severity,
            "metadata": op.metadata,
        }
