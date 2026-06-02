"""
NexusAgent v4.0+ — Social Graph [MIROFISH-INSPIRED]

基于 MiroFish 的 GraphBuilderService 理念：
    - Zep 图谱存储实体-关系网络
    - Agent 共享结构化记忆（谁和谁有关系、关系类型、强度）
    - 用于协作路径发现（A 和 B 有合作关系 → A 可向 B 委托子任务）

来源: MiroFish backend/app/services/graph_builder.py
      Zep 图谱构建 + EntityEdgeSourceTarget

轻量级实现：基于 NetworkX 风格的内存图，无需外部 Zep 依赖
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("nexus.mirofish.social_graph")


@dataclass
class EntityNode:
    """实体节点 — 对应 MiroFish 的 EntityNode"""
    entity_id: str
    name: str
    entity_type: str = "person"  # person | organization | concept | event
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "entity_type": self.entity_type,
            "properties": self.properties,
        }


@dataclass
class RelationEdge:
    """关系边 — 对应 MiroFish 的 EntityEdge"""
    source_id: str
    target_id: str
    relation_type: str = "related"  # collaborates_with | reports_to | influences | conflicts_with
    strength: float = 0.5  # 0-1 关系强度
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "strength": self.strength,
            "properties": self.properties,
        }


class SocialGraph:
    """
    轻量级社会图谱 — Agent 协作关系网络

    Usage:
        graph = SocialGraph()
        graph.add_entity(EntityNode("e1", "市场部", "organization"))
        graph.add_entity(EntityNode("e2", "产品部", "organization"))
        graph.add_relation(RelationEdge("e1", "e2", "collaborates_with", 0.8))

        # 查找协作路径
        path = graph.find_collaboration_path("e1", "e2")
    """

    def __init__(self):
        self._nodes: Dict[str, EntityNode] = {}
        self._edges: Dict[str, List[RelationEdge]] = {}  # source_id -> [edges]
        self._in_edges: Dict[str, List[RelationEdge]] = {}  # target_id -> [edges]

    def add_entity(self, node: EntityNode) -> None:
        """添加实体"""
        self._nodes[node.entity_id] = node
        self._edges.setdefault(node.entity_id, [])
        self._in_edges.setdefault(node.entity_id, [])

    def add_relation(self, edge: RelationEdge) -> None:
        """添加关系"""
        if edge.source_id not in self._nodes:
            logger.warning("关系源节点不存在: %s", edge.source_id)
            return
        if edge.target_id not in self._nodes:
            logger.warning("关系目标节点不存在: %s", edge.target_id)
            return
        self._edges.setdefault(edge.source_id, []).append(edge)
        self._in_edges.setdefault(edge.target_id, []).append(edge)

    def get_entity(self, entity_id: str) -> Optional[EntityNode]:
        return self._nodes.get(entity_id)

    def get_relations(self, entity_id: str, direction: str = "out") -> List[RelationEdge]:
        """获取实体的关系"""
        if direction == "out":
            return self._edges.get(entity_id, [])
        elif direction == "in":
            return self._in_edges.get(entity_id, [])
        else:
            return self._edges.get(entity_id, []) + self._in_edges.get(entity_id, [])

    def find_collaboration_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 3,
    ) -> Optional[List[str]]:
        """
        查找协作路径（BFS）

        Returns:
            节点 ID 列表，如 ["e1", "e3", "e2"]
        """
        if source_id not in self._nodes or target_id not in self._nodes:
            return None

        visited: Set[str] = {source_id}
        queue: List[tuple] = [(source_id, [source_id])]

        while queue:
            current, path = queue.pop(0)
            if current == target_id:
                return path
            if len(path) >= max_depth + 1:
                continue

            for edge in self._edges.get(current, []):
                if edge.target_id not in visited:
                    visited.add(edge.target_id)
                    queue.append((edge.target_id, path + [edge.target_id]))

        return None

    def get_collaboration_strength(self, agent_a: str, agent_b: str) -> float:
        """计算两个 Agent 的协作强度"""
        edges = self._edges.get(agent_a, [])
        for edge in edges:
            if edge.target_id == agent_b and edge.relation_type in ("collaborates_with", "reports_to"):
                return edge.strength
        # 检查反向关系
        edges = self._edges.get(agent_b, [])
        for edge in edges:
            if edge.target_id == agent_a and edge.relation_type in ("collaborates_with", "reports_to"):
                return edge.strength
        return 0.0

    def suggest_collaborators(self, agent_id: str, top_k: int = 3) -> List[tuple]:
        """
        建议协作者

        Returns:
            [(entity_id, strength), ...]
        """
        edges = self._edges.get(agent_id, [])
        candidates = [
            (edge.target_id, edge.strength)
            for edge in edges
            if edge.relation_type in ("collaborates_with", "influences")
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_k]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [
                edge.to_dict()
                for edges in self._edges.values()
                for edge in edges
            ],
        }

    def stats(self) -> Dict[str, Any]:
        return {
            "node_count": len(self._nodes),
            "edge_count": sum(len(e) for e in self._edges.values()),
            "entity_types": list(set(n.entity_type for n in self._nodes.values())),
        }
