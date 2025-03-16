import os
import discord
from discord.ext import commands
import google.generativeai as genai
import requests
import base64
import random
import traceback
import logging
from typing import List
import filetype
import datetime

# Initialize logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)
class GeminiCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        if not self.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        genai.configure(api_key=self.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        print("Gemini Cog Initialized")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return

        if isinstance(message.channel, discord.DMChannel) or self.bot.user.mentioned_in(message):
            await self.process_message(message)

    async def process_message(self, message: discord.Message):
        """Processes a message."""
        image_url = None
        mentions_data = {}

        try:
            if message.attachments:
                logger.info("Attachments DETECTED in message:")
                for attachment in message.attachments:
                    if attachment.content_type and attachment.content_type.startswith('image/'):
                        image_url = attachment.url

            if self.bot.user.mentioned_in(message):
                user_input = message.content.replace(f'<@{self.bot.user.id}>', '').strip()
                mentions_data[self.bot.user.id] = message.author.name
            else:
                user_input = message.content.strip()

            recent_messages = []
            try:
                async for msg in message.channel.history(limit=20, before=message):
                    msg_content = msg.content
                    for mention in msg.mentions:
                        msg_content = msg_content.replace(f"<@{mention.id}>", f"@{mention.name}")
                        mentions_data[mention.id] = msg.author.name
                    for role_mention in msg.role_mentions:
                        msg_content = msg_content.replace(f"<@&{role_mention.id}>", f"@{role_mention.name}")
                    for channel_mention in msg.channel_mentions:
                        msg_content = msg_content.replace(f"<#{channel_mention.id}>", f"#{channel_mention.name}")

                    image_url_in_msg = None
                    for attachment in msg.attachments:
                        if attachment.content_type and attachment.content_type.startswith('image/'):
                            image_url_in_msg = attachment.url
                            break

                    msg_data = {
                        'text': msg_content,
                        'image_url': image_url_in_msg,
                        'author': msg.author.name,
                        'timestamp': msg.created_at,
                        'mentions': mentions_data.copy()
                    }
                    recent_messages.append(msg_data)
                    mentions_data.clear()

            except discord.errors.Forbidden:
                logger.error("Missing permissions to read message history.")
                await message.channel.send("I don't have permission to read message history in this channel.")
                return
            except Exception as e:
                logger.error(f"Error fetching message history: {e}")
                await message.channel.send("An error occurred while fetching message history.")
                return

            recent_messages.reverse()

            current_message_data = {
                'text': user_input,
                'image_url': image_url,
                'author': message.author.name,
                'timestamp': message.created_at,
                'mentions': mentions_data.copy()
            }
            recent_messages.append(current_message_data)

            if len(recent_messages) > 50:
                recent_messages = recent_messages[-50:]

            history_for_prompt = []
            for msg in recent_messages:
                msg_text = msg['text']
                if msg['mentions']:
                    for _, mentioning_user in msg['mentions'].items():
                        msg_text += f" (Mentioned by {mentioning_user})"
                history_for_prompt.append({
                    'text': msg_text,
                    'image_url': msg.get('image_url'),
                    'author': msg['author'],
                    'timestamp': msg['timestamp']
                })

            response = await get_response(user_input, self.model, image_url=image_url, history=history_for_prompt)

            if response:
                # --- Mention Handling (Corrected for DMs) ---
                response_with_mentions = response
                if message.guild:  # Check if it's in a guild (not a DM)
                    for member in message.guild.members:
                        response_with_mentions = response_with_mentions.replace(f"@{member.name}", f"<@{member.id}>")

                await message.channel.send(response_with_mentions)

                bot_response_data = {
                    'text': response,
                    'image_url': None,
                    'author': self.bot.user.name,
                    'timestamp': datetime.datetime.now(datetime.timezone.utc),
                    'mentions': {}
                }
                recent_messages.append(bot_response_data)

            else:
                await message.channel.send("Sorry, I couldn't generate a response.")

        except Exception as e:
            logger.error(f"Exception in process_message: {e}", exc_info=True)
            traceback.print_exc()
            await message.channel.send("Oops! Something went wrong...")

async def get_response(user_input: str, model, image_url=None, history=None) -> str:
    """Gets AI response."""
    logger.info("Entering get_response function")
    lowered: str = user_input.lower()
    if lowered == '':
        return 'Well, you\'re awfully silent...'
    elif 'hello' in lowered:
        return 'Hello there!'
    else:
        personas = [
            "You are a helpful and friendly chatbot on Discord.",
            "You are a witty and sarcastic chatbot on Discord.",
            "You are an enthusiastic and energetic chatbot on Discord.",
            "You are a calm and informative chatbot on Discord.",
        ]
        chosen_persona = random.choice(personas)
        prompt_instructions = "Respond to the following user input concisely.  Consider all parts of the conversation history equally."

        full_prompt_content = ""
        if history:
            full_prompt_content += "Conversation History:\n"
            for turn in history:
                timestamp_str = turn['timestamp'].strftime("%Y-%m-%d %H:%M:%S UTC")
                role_prefix = f"{turn['author']} ({timestamp_str}):"
                content_text = turn['text']
                turn_image_url = turn.get('image_url')

                if turn_image_url:
                    full_prompt_content += f"{role_prefix} [Image Attached] {content_text}\n"
                else:
                    full_prompt_content += f"{role_prefix} {content_text}\n"
            full_prompt_content += "\n"

        full_prompt_content += f"{chosen_persona} {prompt_instructions} User input: '{user_input}'"
        if image_url:
            full_prompt_content += f"\n\nThere is an image attached to this message. Please analyze the image and incorporate your analysis into your response."
            logger.info(f"Image instruction added to prompt: {full_prompt_content}")

        return await generate_gemini_response(full_prompt_content, model, image_url)
    pass

async def generate_gemini_response(prompt: str, model, image_url: str = None) -> str:
    """Generates response from Gemini API."""
    logger.info("Entering generate_gemini_response function")
    logger.info(f"Prompt to Gemini: {prompt}, Image URL: {image_url}")

    content_parts: List[dict] = []
    content_parts.append({"text": prompt})

    if image_url:
        try:
            logger.info(f"Fetching image from URL: {image_url}")
            image_response = requests.get(image_url, stream=True)
            image_response.raise_for_status()
            image_data = image_response.content
            kind = filetype.guess(image_data)
            if kind is None:
                logger.warning("Could not determine image type. Defaulting to png.")
                mime_type = "image/png"
            else:
                mime_type = kind.mime

            content_parts.append({"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_data).decode()}})
            logger.info(f"Image fetched and added to content parts (type: {mime_type}).")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching image: {e}")
            return "I couldn't download the image. Please check the link."
        except Exception as e:
            logger.exception(f"Unexpected error fetching/processing image: {e}")
            return "An unexpected error occurred while processing the image."

    try:
        logger.info("Sending request to Gemini API...")
        response = model.generate_content(contents=content_parts, generation_config=genai.types.GenerationConfig(max_output_tokens=200))
        return response.text
    except Exception as e:
        logger.error(f"Error with Gemini API: {e}", exc_info=True)
        return "I'm having trouble with Gemini right now. Try again later."
        pass

async def setup(bot: commands.Bot):
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY not found in environment variables. Gemini Cog will not be loaded.")
        return  # Exit the setup function without loading the cog

    try:
        # Only initialize and add the cog if the API key is present
        await bot.add_cog(GeminiCog(bot))
        print("Gemini Cog loaded!")
    except ValueError as e:
        print(f"Gemini Cog could not be loaded: {e}") # Catch the ValueError from GeminiCog init if it still occurs after checking above
        print("Please ensure GEMINI_API_KEY is set correctly in your environment variables.")
        return # Exit setup if there's a ValueError during cog initialization
    except Exception as e:
        print(f"An unexpected error occurred during Gemini Cog setup: {e}")
        return # Exit setup if any other error occurs