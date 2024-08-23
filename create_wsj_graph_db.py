import dotenv
import os
from langchain_community.graphs import Neo4jGraph
from langchain.text_splitter import CharacterTextSplitter
import requests
from openai import OpenAI

# load environment variables
load_status = dotenv.load_dotenv(".env")
if load_status is False:
    raise RuntimeError('Environment variables are not found.')

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv('NEO4J_USERNAME')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD')
NEO4J_DATABASE = os.getenv('NEO4J_DATABASE')
RAPID_API_KEY = os.getenv('RAPID_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

VECTOR_INDEX_NAME = 'wsj_articles'

# database connection
graph = Neo4jGraph(
    url=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD, database=NEO4J_DATABASE
)

# make a search to WSJ Rapid API using a searchword
searchword = input("Give a search word: ")

# searchwrod can be a good choice for the node name
node = input("Do you want to create or link this search word to some existing node? If yes, please give the node name. If no, then leave this field empty: ")


if node != "":
    print("Creating search node ", node)
    create_node = """
    MERGE (node:Node {nodename: $name })
    ON CREATE 
        SET node.created = "auto"
    """
    graph.query(create_node, params={'name': node})

    graph.query("""
        CREATE CONSTRAINT unique_node IF NOT EXISTS 
        FOR (node:Node) REQUIRE node.nodename IS UNIQUE
    """)    

    # node can also be linked to some parent node
    masternode = input(f"Do you want to link the node {node} to some parent node? If yes, please give the master node name. If no, then leave this field empty: ")

    if masternode != "":
        print("Creating parent node ",masternode)
        create_master_node = """
        MERGE (node:Masternode {nodename: $name })
        ON CREATE 
            SET node.created = "auto"
        """
        graph.query(create_master_node, params={'name': masternode})

        graph.query("""
            CREATE CONSTRAINT unique_masternode IF NOT EXISTS 
            FOR (node:Masternode) REQUIRE node.nodename IS UNIQUE
        """)


# connect to WSJ rapid API
querystring = {"keyword": searchword}

wsj_url = "https://wall-street-journal.p.rapidapi.com/api/v1/searchArticleByKeyword"
headers = {
	"x-rapidapi-key": RAPID_API_KEY,
	"x-rapidapi-host": "wall-street-journal.p.rapidapi.com"
}

response = requests.get(wsj_url, headers=headers, params=querystring)
response_data = response.json()
# Rapid API returns a list of article ids
article_ids = [article['articleId'] for article in response_data['data']]

# articles are split into chunks
text_splitter = CharacterTextSplitter(
    chunk_size = 1000,
    chunk_overlap  = 100
)

# create chunks from metadata
def split_text(data):
    metadata = []
    for item in data:
        articleid = item['id']
        language = item['language']
        articlewordcount = item['articleWordCount']
        pubdate = item['pubdate']
        majorrevisiondate = item['majorRevisionDate']
        pubdatenumber = item['pubdateNumber']
        lastpubdate = item['lastPubdate']
        lastpubdatenumber = item['lastPubdateNumber']
        origpubdate = item['origPubdate']
        origpubdatenumber = item['origPubdateNumber']
        headline = item['headline']
        grouphed = item['grouphed']
        socialhed = item['socialhed']
        subhed = item['subhed']
        summary = item['summary']
        text = item['bodyExtract']
        sharelink = item['shareLink']
        category = item['category']
        subcategory = item['subCategory']
        authorid = item['authorID']
        readtome = item['readToMe']
        variants = item['variants']
        authors = item['authors']
        
        text_chunks = text_splitter.split_text(text)
        counter = 0
        for chunk in text_chunks:
            metadata.append({
                'text': chunk,
                'articleId': articleid,
                'chunkId': f'{articleid}--chunk{counter:04d}',
                'chunkSeqId': counter,
                'source': articleid,
                'language': language,
                'articlewordcount': articlewordcount,
                'pubdate': pubdate,
                'majorrevisiondate': majorrevisiondate,
                'pubdatenumber': pubdatenumber,
                'lastpubdate': lastpubdate,
                'lastpubdatenumber': lastpubdatenumber,
                'origpubdate': origpubdate,
                'origpubdatenumber': origpubdatenumber,
                'headline': headline,
                'grouphed': grouphed,
                'socialhed': socialhed,
                'subhed': subhed,
                'summary': summary,
                'sharelink': sharelink,
                'category': category,
                'subcategory': subcategory,
                'authorid': authorid,
                'readtome': readtome,
                'ariants': variants,
                'authors': authors
            })
            print(f'{articleid}--chunk{counter:04d}')
            counter += 1
        print(f'\tSplit into {counter} chunks')
    return metadata

# create the same chunks to neo4j
create_chunks = """
MERGE(Chunks:Chunk {chunkId: $chunkParam.chunkId})
    ON CREATE SET 
        Chunks.text = $chunkParam.text,
        Chunks.articleId = $chunkParam.articleId, 
        Chunks.chunkSeqId = $chunkParam.chunkSeqId,
        Chunks.source = $chunkParam.source, 
        Chunks.language = $chunkParam.language,
        Chunks.articlewordcount = $chunkParam.articleWordCount,
        Chunks.pubdate = $chunkParam.pubdate,
        Chunks.majorrevisiondate = $chunkParam.majorRevisionDate,
        Chunks.pubdate_number = $chunkParam.pubdateNumber,
        Chunks.lastpubdate = $chunkParam.lastPubdate,
        Chunks.lastpubdate_number = $chunkParam.lastPubdateNumber,
        Chunks.origpubdate = $chunkParam.origPubdate,
        Chunks.origpubdatenumber = $chunkParam.origPubdateNumber,
        Chunks.headline = $chunkParam.headline,
        Chunks.grouphed = $chunkParam.grouphed,
        Chunks.socialhed = $chunkParam.socialhed,
        Chunks.subhed = $chunkParam.subhed,
        Chunks.summary = $chunkParam.summary,
        Chunks.sharelink = $chunkParam.shareLink,
        Chunks.category = $chunkParam.category,
        Chunks.subcategory = $chunkParam.subCategory,
        Chunks.authorid = $chunkParam.authorID,
        Chunks.readtome = $chunkParam.readToMe,
        Chunks.variants = $chunkParam.variants,
        Chunks.authors = $chunkParam.authors
RETURN Chunks
"""

graph.query("""
CREATE CONSTRAINT unique_chunk IF NOT EXISTS 
    FOR (c:Chunk) REQUIRE c.chunkId IS UNIQUE
""")

# search individual articles
wsj_id_url = "https://wall-street-journal.p.rapidapi.com/api/v1/getArticleDetails"

print("Creating chunks")
for article_id in article_ids:
    print(article_id)
    querystring = {"articleId": article_id}
    resp_article = requests.get(wsj_id_url, headers=headers, params=querystring)
    article_data = resp_article.json()['data']
    list_of_chunks = split_text([article_data])
    for chunk in list_of_chunks:
        graph.query(create_chunks, params={'chunkParam': chunk})


# if an articles consists of several chunks, this creates a link between the chunks
create_chunk_link = """
  MATCH (from_same_article:Chunk)
    WHERE from_same_article.articleId = $articleId
  WITH from_same_article
    ORDER BY from_same_article.chunkSeqId ASC
  WITH collect(from_same_article) as section_chunk_list
    CALL apoc.nodes.link(
       section_chunk_list,
       "NEXT",
       {avoidDuplicates: true}
    )
  RETURN size(section_chunk_list)
"""

# create relationship to parent node
create_parent_relationships = """
  MATCH (c:Chunk), (n:Node)
  WHERE c.articleId = $article_id
    AND n.nodename = $node_name  
  MERGE (c)-[newRelationship:PART_OF]->(n)
  RETURN count(newRelationship)
"""

# create a link from parent node to the first chunk
create_link_to_first_chunk = """
  MATCH (first:Chunk), (n:Node)
  WHERE first.articleId = $article_id
    AND first.chunkSeqId = 0
    AND n.nodename = $node_name
  WITH first, n
    MERGE (n)-[r:FIRST_CHUNK]->(first)
  RETURN count(r)
"""

# iterate through all the articles and create the necessary links
for article_id in article_ids:
    print("Creating chunk links for artice ",article_id)
    graph.query(create_chunk_link, params = {'articleId': article_id})
    if node != "":
        print("Creating links from chunks to parent ",node)
        graph.query(create_parent_relationships, params={'article_id': article_id, 'node_name': node})
        print("Creating link from parent ",node," to first chunk")
        graph.query(create_link_to_first_chunk, params={'article_id': article_id, 'node_name': node})

# create a parent node
if masternode !="":
    create_master_relationship = """
        MATCH (n:Node), (m:Masternode)
        WHERE n.nodename = $nodename
          AND m.nodename = $masternode  
        MERGE (n)-[newRelationship:PART_OF]->(m)
        RETURN count(newRelationship)
    """
    print("Creating a link from ",node," to parent ",masternode)
    graph.query(create_master_relationship, params={'nodename': node, 'masternode': masternode})


client = OpenAI()

# embeddings for text
def get_embedding(text, model="text-embedding-3-small"):
   text = text.replace("\n", " ")
   return client.embeddings.create(input = [text], model=model).data[0].embedding

# text embessings are updated to all chunks
def update_text_embeddings():
    # Fetch chunks with NULL textEmbedding
    query = "MATCH (chunk:Chunk) WHERE chunk.textEmbedding IS NULL RETURN chunk"
    chunks = graph.query(query)

    for record in chunks:
        chunk = record['chunk']
        text = chunk['text']
        vector = get_embedding(text)

        # Update the chunk with the encoded vector
        update_query = """
        MATCH (chunk:Chunk {chunkId: $chunkId})
        SET chunk.textEmbedding = $vector
        """
        graph.query(update_query, params={"chunkId": chunk['chunkId'], "vector": vector})


print("Creating text embeddings for chunks.")
update_text_embeddings()