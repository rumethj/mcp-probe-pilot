import asyncio
import sys

from langchain_core.messages import HumanMessage, ToolMessage

from mcp_probe_pilot.core.mcp_session import MCPSession
from mcp_probe_pilot.core.llm_client import LLMClient

class MCPClient:
    """A client that integrates an MCP Server with a Gemini LLM via LangChain.
    
    This handles the chat loop, formats MCP tools for LangChain, and automatically 
    executes requested tool calls against the MCP Session.
    """
    def __init__(self, mcp_session: MCPSession, llm_client: LLMClient):
        self.mcp_session = mcp_session
        self.llm_client = llm_client
        self.chat_history =[]
        self._tools_cache = None

    async def get_available_tools(self) -> list[dict]:
        """Fetch tools from the MCP server and format them for LangChain."""
        if self._tools_cache is not None:
            return self._tools_cache

        # Fetch tools from MCP server
        result = await self.mcp_session.list_tools()
        
        # Convert MCP tools to LangChain/OpenAI compatible schema format
        self._tools_cache =[
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                }
            }
            for tool in result.tools
        ]
        return self._tools_cache

    async def process_query(self, llm, query: str) -> str:
        """Process a single query, handling multiple back-and-forth tool calls."""
        tools = await self.get_available_tools()
        
        # Bind tools to the LLM if any are available
        llm_with_tools = llm.bind_tools(tools) if tools else llm

        # Add the user's message to our chat history
        self.chat_history.append(HumanMessage(content=query))
        final_text =[]

        while True:
            # Generate response from Gemini
            response = await llm_with_tools.ainvoke(self.chat_history)
            self.chat_history.append(response)

            # Keep track of text chunks sent back by the LLM
            if response.content:
                final_text.append(response.content)

            # If Gemini didn't ask to use any tools, we've reached the final answer
            if not response.tool_calls:
                break

            # Handle requested tool calls
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]

                final_text.append(f"\n[Calling tool '{tool_name}' with args {tool_args}]")

                try:
                    # Execute tool against the MCP Server
                    tool_result = await self.mcp_session.call_tool(tool_name, tool_args)
                    
                    # CallToolResult content is a list of TextContent/ImageContent.
                    # We extract the text properties to feed back to the LLM.
                    result_text = "\n".join(
                        item.text 
                        for item in tool_result.content 
                        if getattr(item, "type", "text") == "text"
                    )
                except Exception as e:
                    result_text = f"Error executing tool {tool_name}: {str(e)}"

                # Provide the tool execution results back to the LLM
                self.chat_history.append(
                    ToolMessage(
                        content=result_text,
                        tool_call_id=tool_id,
                        name=tool_name
                    )
                )

        return "\n".join(final_text)

    async def chat_loop(self):
        """Run an interactive chat loop."""
        print("\nMCP Client Started!")
        tools = await self.get_available_tools()
        tool_names = [t["function"]["name"] for t in tools]
        print(f"Connected to MCP server with tools: {tool_names}")
        print("Type your queries or 'quit' to exit.")

        # The LLMClient is a synchronous context manager, while MCPSession is async.
        # Entering it here ensures `.close()` is cleanly fired only when the chat loop exits.
        with self.llm_client as llm:
            while True:
                try:
                    query = input("\nQuery: ").strip()

                    if query.lower() == "quit":
                        break
                    
                    if not query:
                        continue

                    response = await self.process_query(llm, query)
                    print("\n" + response)

                except KeyboardInterrupt:
                    print("\nExiting...")
                    break
                except Exception as e:
                    print(f"\nError processing query: {str(e)}")