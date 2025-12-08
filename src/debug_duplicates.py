
import os
import sys
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

def check_duplicates():
    load_dotenv()
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    with driver.session() as session:
        # Check Normativa duplicates
        query = """
        MATCH (n:Normativa)
        WITH n.id as id, count(n) as c
        WHERE c > 1
        RETURN id, c
        """
        result = session.run(query)
        print("Normativa Duplicates:")
        for record in result:
            print(record)
            
        # Check Materia duplicates
        query = """
        MATCH (n:Materia)
        WITH n.id as id, count(n) as c
        WHERE c > 1
        RETURN id, c
        """
        result = session.run(query)
        print("\nMateria Duplicates:")
        for record in result:
            print(record)

        # Check Article duplicates
        query = """
        MATCH (n:articulo)
        WITH n.id as id, count(n) as c
        WHERE c > 1
        RETURN id, c
        """
        result = session.run(query)
        print("\nArticle Duplicates:")
        for record in result:
            print(record)
            
    driver.close()

if __name__ == "__main__":
    check_duplicates()
