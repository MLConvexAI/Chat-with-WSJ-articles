import dotenv
import os
from langchain_community.graphs import Neo4jGraph
from openai import OpenAI
import gradio as gr

VECTOR_INDEX_NAME = 'wsj_articles'

client = OpenAI()

# load environment variables
load_status = dotenv.load_dotenv(".env")
if load_status is False:
    raise RuntimeError('Environment variables are not found.')

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv('NEO4J_USERNAME')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD')
NEO4J_DATABASE = os.getenv('NEO4J_DATABASE')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

VECTOR_INDEX_NAME = 'wsj_articles'

# make a connection Neo4j graph database
graph = Neo4jGraph(
    url=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD, database=NEO4J_DATABASE
)

# create embedding for text
def get_embedding(text, model="text-embedding-3-small"):
    text = text.replace("\n", " ")
    return client.embeddings.create(input=[text], model=model).data[0].embedding

# vector search to neo4j database
def neo4j_vector_search(question):

    # Encode the question to get the embedding
    question_embedding = get_embedding(question)

    # Perform the vector search using the encoded embedding
    vector_search_query = """
    CALL db.index.vector.queryNodes($index_name, $top_k, $question_embedding) YIELD node, score
    RETURN score, node.text AS text
    """
    similar = graph.query(vector_search_query, 
                       params={
                        'question_embedding': question_embedding, 
                        'index_name': VECTOR_INDEX_NAME, 
                        'top_k': 10})
    return similar

# generate answer to the question
def create_answer(question):

    # first find the best answers from graph database
    search_results = neo4j_vector_search(question)

    messages = []
    system_instructions = """You assist user to create summaries and asks questions based on the CONTEXT: documents. Use vector index scores to find the most relevant answer to user question. If you do not know, answer 'I don't know.'""" 
    messages.append(
                    {
                        "role": "system", 
                        "content": system_instructions
                    })

    prompt_template = """{question} \n\nCONTEXT: {search_results}"""
    messages.append(
                    {
                        "role": "user", 
                        "content": prompt_template.format(question=question, search_results=search_results)
                    })

    # Openai response generation
    response = client.chat.completions.create(
                model = "gpt-4o-2024-05-13",
                messages = messages,
                temperature = 0.1,
                max_tokens = 2048,
                top_p = 1.0)
    return response.choices[0].message.content

# clear button in gradio interface
def clear_fields():
    return "", ""

# Create the Gradio interface
with gr.Blocks() as demo:
    question = gr.Textbox(label="Question", lines=3)
    submit_btn = gr.Button("Submit")
    output = gr.Textbox(label="WSJ Articles answer", lines=15)
    clear_btn = gr.Button("Clear")

    submit_btn.click(create_answer, inputs=[question], outputs=[output])
    clear_btn.click(clear_fields, inputs=[], outputs=[question, output])

# lauch the gradio application
demo.launch(share=True)

