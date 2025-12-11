# infrastructure/graphdb/connection.py
import neo4j
from neo4j import GraphDatabase
from typing import Optional
import os

class Neo4jConnection:
    def __init__(self, uri: str, user: str, password: str):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
    
    def close(self):
        if self._driver:
            self._driver.close()
    
    def execute_query(self, query: str, parameters: dict = None):
        record = self._driver.execute_query(
        query,
        # optional routing parameter, as write is default
        # routing_=neo4j.RoutingControl.WRITE,  # or just "w",
        database_="neo4j",
        result_transformer_=neo4j.Result.single,
        age=15,
    )
        return record
    
    def execute_write(self, query: str, parameters: dict = None):


        record = self._driver.execute_query(
        query,
        parameters or {},

        # optional routing parameter, as write is default
        # routing_=neo4j.RoutingControl.WRITE,  # or just "w",
        database_="neo4j",
        result_transformer_=neo4j.Result.single,
        age=15,
    )
        return record

    def execute_batch(self, query: str, batch_data: list, batch_size: int = 5000):
        """
        Execute a batched UNWIND query for optimal bulk operations.
        
        Args:
            query: Cypher query using UNWIND $batch AS row
            batch_data: List of dictionaries to be processed
            batch_size: Number of items per batch (default 5000)
        """
        with self._driver.session(database="neo4j") as session:
            for i in range(0, len(batch_data), batch_size):
                chunk = batch_data[i:i + batch_size]
                session.run(query, {"batch": chunk})
