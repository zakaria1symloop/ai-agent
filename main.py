from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import asyncio
import websockets
import json
import base64
import logging
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
from elevenlabs.client import ElevenLabs
from typing import Dict, Set
import time
import uuid
from dataclasses import dataclass, field
from collections import defaultdict

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="AI Voice Assistant Platform")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "G1QUjBCuRBbLbAmYlTgl")

# Validate required environment variables
if not OPENAI_API_KEY:
    logger.error("❌ OPENAI_API_KEY environment variable is required")
if not ELEVENLABS_API_KEY:
    logger.error("❌ ELEVENLABS_API_KEY environment variable is required")

# Initialize clients with error handling
try:
    if OPENAI_API_KEY and ELEVENLABS_API_KEY:
        openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        SERVICES_AVAILABLE = True
        logger.info("✅ AI services initialized successfully")
    else:
        openai_client = None
        elevenlabs_client = None
        SERVICES_AVAILABLE = False
        logger.error("❌ Missing required API keys in environment variables")
except Exception as e:
    logger.error(f"❌ Failed to initialize AI services: {e}")
    openai_client = None
    elevenlabs_client = None
    SERVICES_AVAILABLE = False

# Role configurations 
ROLE_CONFIGS = {
    "police_call": {
        "system_prompt": """مرحباً بكم في نظامنا Voris AI المطور من قبل الأستاذ عمراني زكريا.

أنت موظف استقبال بلاغات في مركز شرطة داخل دولة الإمارات.
- ابدأ كل محادثة بالترحيب والتعريف بدورك دون ذكر اسمك الشخصي
- تعامل مع جميع البلاغات بجدية ومهنية عالية
- اجمع المعلومات الأساسية بسرعة وبشكل منهجي:
  * الموقع الدقيق للحادث
  * نوع البلاغ والتفاصيل الأساسية
  * عدد المصابين أو المتضررين إن وجد
  * مدى خطورة الوضع
- استخدم أسئلة قصيرة وواضحة ومباشرة
- طمئن المتصل بأن الفرق المختصة ستصل في أقرب وقت
- احتفظ بهدوئك مهما كانت حالة المتصل أو طبيعة البلاغ
- استخدم اللهجة الإماراتية المناسبة والمهنية
- لا تفصح عن هويتك الشخصية أو تستخدم أسماء وهمية""",
        "max_tokens": 180,
        "temperature": 0.2
    },
    
    "police_interview": {
        "system_prompt": """مرحباً بكم في نظامنا Voris AI المطور من قبل الأستاذ عمراني زكريا.

أنت محقق جنائي في شرطة أبوظبي، تقوم بإجراء مقابلة رسمية مع مشتبه به أو شاهد.
- ابدأ بالتعريف بدورك كمحقق والغرض من المقابلة دون ذكر اسم شخصي
- اشرح للشخص حقوقه القانونية بوضوح
- استخدم أسئلة متسلسلة ومنطقية بناءً على الإجابات المستلمة
- لا تقاطع المتحدث واستمع بانتباه كامل
- اطلب توضيحات إضافية عند الحاجة أو عدم الوضوح
- لاحظ أي تناقضات أو تفاصيل مهمة في الأقوال
- سجّل كل ما يُقال بدقة ووضوح
- تحدث بلهجة رسمية إماراتية مع الحفاظ على الاحترام
- لا تفترض الإدانة وحافظ على الموضوعية""",
        "max_tokens": 220,
        "temperature": 0.3
    },
    
    "customer_service": {
        "system_prompt": """مرحباً بكم في نظامنا Voris AI المطور من قبل الأستاذ عمراني زكريا.

أنت ممثل خدمة عملاء في شركة إماراتية محترمة.
- استقبل العميل بترحيب حار وبلهجة إماراتية ودودة ومهنية
- لا تذكر اسمك الشخصي، بل عرّف نفسك كممثل خدمة عملاء
- اسأل عن المشكلة أو الاستفسار بشكل مباشر وواضح
- استمع بعناية لكل التفاصيل قبل تقديم الحلول
- قدّم حلول عملية ومتعددة البدائل حسب الإمكان
- تأكد من فهمك الكامل للمشكلة قبل الرد أو اقتراح الحلول
- اعتذر بلباقة وصدق إن كان هناك تأخير أو خطأ من الشركة
- اطلب التأكيد من العميل على فهم الحل المقترح
- هدفك الأساسي: تحقيق رضا العميل الكامل قبل إنهاء المحادثة
- استخدم لغة مهذبة ومحترمة في جميع الأوقات""",
        "max_tokens": 200,
        "temperature": 0.4
    },
    
    # إعدادات إضافية للنظام
    "general_settings": {
        "welcome_message": "مرحباً بكم في نظامنا Voris AI المطور من قبل الأستاذ عمراني زكريا",
        "identity_guidelines": [
            "لا تذكر أي أسماء شخصية أو وهمية لنفسك",
            "عرّف نفسك بدورك الوظيفي فقط",
            "استخدم عبارات مثل 'أنا هنا لمساعدتكم' بدلاً من 'اسمي...'",
            "حافظ على الطابع المهني في جميع التفاعلات"
        ],
        "response_quality": {
            "clarity": "استخدم لغة واضحة ومباشرة",
            "professionalism": "حافظ على المهنية في جميع الأوقات",
            "cultural_sensitivity": "راع الثقافة والتقاليد الإماراتية",
            "efficiency": "كن سريعاً في الاستجابة ودقيقاً في المعلومات"
        }
    }
}

# Global state
active_sessions: Dict[str, "VoiceSession"] = {}
conversation_histories: Dict[str, list] = defaultdict(list)

@dataclass
class VoiceSession:
    """Enhanced voice session with role support"""
    session_id: str
    websocket: WebSocket
    role: str = "customer_service"  # Default role
    openai_ws: websockets.WebSocketServerProtocol = None
    is_connected: bool = False
    is_processing_response: bool = False
    is_generating_audio: bool = False
    audio_buffer: list = field(default_factory=list)
    pending_transcripts: Set[str] = field(default_factory=set)
    last_transcript_time: float = 0
    
    # Voice settings
    voice_id: str = ELEVENLABS_VOICE_ID
    
    # Performance tracking
    stats: dict = field(default_factory=lambda: {
        'transcripts_processed': 0,
        'responses_generated': 0,
        'audio_chunks_sent': 0,
        'total_latency': [],
        'session_start': time.time()
    })

    async def connect_to_openai(self):
        """Connect to OpenAI Realtime API with error handling"""
        if not SERVICES_AVAILABLE or not openai_client:
            await self.websocket.send_json({
                "type": "system_offline",
                "message": "خدمة الذكاء الاصطناعي غير متاحة حالياً"
            })
            return

        uri = "wss://api.openai.com/v1/realtime?intent=transcription"
        
        try:
            self.openai_ws = await websockets.connect(
                uri,
                subprotocols=[
                    "realtime",
                    f"openai-insecure-api-key.{OPENAI_API_KEY}",
                    "openai-beta.realtime-v1"
                ],
                ping_interval=30,
                ping_timeout=10,
                close_timeout=10
            )
            
            # Configure session for optimal performance
            config = {
                "type": "transcription_session.update",
                "session": {
                    "input_audio_format": "pcm16",
                    "input_audio_transcription": {
                        "model": "gpt-4o-transcribe",
                        "prompt": "Transcribe speech accurately. Wait for complete thoughts. Handle Arabic and English."
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 800  # No interruptions
                    }
                }
            }
            
            await self.openai_ws.send(json.dumps(config))
            self.is_connected = True
            
            logger.info(f"✅ OpenAI connected for session {self.session_id} with role {self.role}")
            await self.websocket.send_json({
                "type": "status", 
                "message": "متصل! النظام جاهز للعمل"
            })
            
            # Start listening for OpenAI messages
            asyncio.create_task(self.listen_openai_messages())
            
        except Exception as e:
            logger.error(f"OpenAI connection failed: {e}")
            await self.websocket.send_json({
                "type": "error", 
                "message": "فشل في الاتصال بخدمة الذكاء الاصطناعي"
            })

    async def listen_openai_messages(self):
        """Listen for OpenAI WebSocket messages with error handling"""
        try:
            async for message in self.openai_ws:
                data = json.loads(message)
                event_type = data.get('type')
                await self.handle_openai_event(event_type, data)
                
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"OpenAI connection closed for {self.session_id}")
        except Exception as e:
            logger.error(f"Error listening to OpenAI: {e}")
            await self.websocket.send_json({
                "type": "error",
                "message": "حدث خطأ في خدمة النسخ الصوتي"
            })

    async def handle_openai_event(self, event_type: str, data: dict):
        """Handle OpenAI events with no-interruption logic"""
        
        if event_type == 'transcription_session.updated':
            await self.websocket.send_json({
                "type": "status", 
                "message": "النظام جاهز للمحادثة!"
            })
        
        elif event_type == 'input_audio_buffer.speech_started':
            if not self.is_generating_audio:
                await self.websocket.send_json({
                    "type": "voice_activity", 
                    "status": "speech_started"
                })
            else:
                logger.info("🚫 Speech detected during audio generation - ignoring")
        
        elif event_type == 'input_audio_buffer.speech_stopped':
            if not self.is_generating_audio:
                await self.websocket.send_json({
                    "type": "voice_activity", 
                    "status": "speech_stopped"
                })
        
        elif event_type == 'conversation.item.input_audio_transcription.completed':
            transcript = data.get('transcript', '').strip()
            item_id = data.get('item_id')
            
            if transcript and item_id and not self.is_generating_audio:
                await self.handle_transcript(transcript, item_id)
            elif self.is_generating_audio:
                logger.info(f"🚫 Transcript ignored during audio generation: {transcript}")
        
        elif event_type == 'error':
            error_msg = data.get('error', {}).get('message', 'Unknown error')
            logger.error(f"OpenAI error: {error_msg}")
            await self.websocket.send_json({
                "type": "error", 
                "message": "حدث خطأ في معالجة الصوت"
            })

    async def handle_transcript(self, transcript: str, item_id: str):
        """Handle transcription with deduplication, response generation, and time limit check"""
        # Check session time limit first
        if self.check_session_time_limit():
            await self.websocket.send_json({
                "type": "session_expired",
                "message": "انتهت مدة المحادثة المسموحة (دقيقة ونصف)"
            })
            logger.info(f"Session {self.session_id} expired after 1.5 minutes")
            return
        
        transcript_key = f"{item_id}_{transcript}"
        
        if transcript_key in self.pending_transcripts:
            return
            
        current_time = time.time()
        if current_time - self.last_transcript_time < 1.0:
            return
            
        self.pending_transcripts.add(transcript_key)
        self.last_transcript_time = current_time
        
        logger.info(f"📝 Processing transcript for {self.role}: {transcript}")
        self.stats['transcripts_processed'] += 1
        
        # Send transcript to client immediately
        await self.websocket.send_json({
            "type": "transcript", 
            "text": transcript
        })
        
        # Start response generation
        self.is_processing_response = True
        await self.generate_ai_response(transcript)

    async def generate_ai_response(self, transcript: str):
        """Generate AI response with role-specific behavior"""
        try:
            if not SERVICES_AVAILABLE or not openai_client:
                await self.websocket.send_json({
                    "type": "error",
                    "message": "خدمة الذكاء الاصطناعي غير متاحة"
                })
                return

            start_time = time.time()
            
            await self.websocket.send_json({
                "type": "ai_response_start"
            })
            
            # Get conversation history and role config
            conversation_history = conversation_histories[self.session_id]
            conversation_history.append({"role": "user", "content": transcript})
            
            role_config = ROLE_CONFIGS.get(self.role, ROLE_CONFIGS["customer_service"])
            
            # Generate response with role-specific settings
            stream = await openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": role_config["system_prompt"]}
                ] + conversation_history[-10:],
                max_tokens=role_config["max_tokens"],
                temperature=role_config["temperature"],
                stream=True,
                timeout=15
            )
            
            complete_response = ""
            
            async for chunk in stream:
                if not self.is_processing_response:
                    break
                    
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    complete_response += content
                    
                    await self.websocket.send_json({
                        "type": "ai_response_delta", 
                        "text": content
                    })
            
            # Complete the text response
            if self.is_processing_response and complete_response.strip():
                conversation_history.append({
                    "role": "assistant", 
                    "content": complete_response.strip()
                })
                
                response_time = time.time() - start_time
                self.stats['responses_generated'] += 1
                self.stats['total_latency'].append(response_time)
                
                await self.websocket.send_json({
                    "type": "ai_response_end",
                    "response_time": round(response_time, 3),
                    "word_count": len(complete_response.split())
                })
                
                logger.info(f"✅ {self.role} response generated in {response_time:.3f}s")
                
                # Generate and stream audio
                await self.generate_and_stream_audio(complete_response.strip())
            
            self.is_processing_response = False
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            await self.websocket.send_json({
                "type": "error", 
                "message": "حدث خطأ في توليد الرد"
            })
            self.is_processing_response = False

    async def generate_and_stream_audio(self, text: str):
        """Generate audio with ElevenLabs and stream to frontend with enhanced error handling"""
        if not text.strip():
            return
            
        try:
            if not SERVICES_AVAILABLE or not elevenlabs_client:
                await self.websocket.send_json({
                    "type": "error",
                    "message": "خدمة تحويل النص إلى كلام غير متاحة"
                })
                return
            
            # Set audio generation flag
            self.is_generating_audio = True
            
            logger.info(f"🎵 Generating audio for {self.role}: {text[:50]}...")
            
            # Generate audio stream with ElevenLabs
            audio_stream = elevenlabs_client.text_to_speech.stream(
                text=text,
                voice_id=self.voice_id,
                model_id="eleven_turbo_v2_5",
                output_format="mp3_44100_128",
                optimize_streaming_latency=0,  # Better quality, less aggressive optimization
                voice_settings={
                    "stability": 0.8,
                    "similarity_boost": 0.85,
                    "style": 0.2,
                    "use_speaker_boost": True
                }
            )
            
            chunk_count = 0
            chunk_buffer = bytearray()
            target_chunk_size = 25000  # Increased to 16KB chunks for smoother playback
            
            # Stream audio chunks to frontend with buffering
            for chunk in audio_stream:
                if isinstance(chunk, bytes) and len(chunk) > 0:
                    chunk_buffer.extend(chunk)
                    
                    while len(chunk_buffer) >= target_chunk_size:
                        send_chunk = bytes(chunk_buffer[:target_chunk_size])
                        chunk_buffer = chunk_buffer[target_chunk_size:]
                        
                        base64_audio = base64.b64encode(send_chunk).decode('utf-8')
                        
                        await self.websocket.send_json({
                            "type": "audio_chunk",
                            "audio": base64_audio,
                            "chunk_size": len(send_chunk)
                        })
                        
                        chunk_count += 1
                        self.stats['audio_chunks_sent'] += 1
                        
                        # Slightly reduced delay for smoother streaming
                        await asyncio.sleep(0.003)
            
            # Send any remaining buffered data
            if len(chunk_buffer) > 0:
                base64_audio = base64.b64encode(bytes(chunk_buffer)).decode('utf-8')
                
                await self.websocket.send_json({
                    "type": "audio_chunk",
                    "audio": base64_audio,
                    "chunk_size": len(chunk_buffer)
                })
                
                chunk_count += 1
                self.stats['audio_chunks_sent'] += 1
            
            # Signal completion
            await self.websocket.send_json({
                "type": "audio_complete",
                "total_chunks": chunk_count
            })
            
            logger.info(f"🎵 {self.role} audio streaming completed - {chunk_count} larger chunks sent")
            
        except Exception as e:
            logger.error(f"Audio generation error: {e}")
            await self.websocket.send_json({
                "type": "error", 
                "message": "حدث خطأ في توليد الصوت"
            })
        finally:
            self.is_generating_audio = False

    def check_session_time_limit(self) -> bool:
        """Check if session has exceeded 1.5 minute limit"""
        elapsed_time = time.time() - self.stats['session_start']
        return elapsed_time > 90  # 1.5 minutes = 90 seconds

    async def send_audio_chunk(self, audio_data: bytes):
        """Send audio chunk to OpenAI - only if not generating TTS and within time limit"""
        if not self.is_connected or not self.openai_ws or self.is_generating_audio:
            return
        
        # Check session time limit
        if self.check_session_time_limit():
            await self.websocket.send_json({
                "type": "session_expired",
                "message": "انتهت مدة المحادثة المسموحة"
            })
            return
            
        try:
            base64_audio = base64.b64encode(audio_data).decode('utf-8')
            
            audio_event = {
                "type": "input_audio_buffer.append",
                "audio": base64_audio
            }
            
            await self.openai_ws.send(json.dumps(audio_event))
            
        except Exception as e:
            logger.error(f"Error sending audio: {e}")

    async def close(self):
        """Clean shutdown with stats logging"""
        self.is_connected = False
        self.is_processing_response = False
        self.is_generating_audio = False
        
        if self.openai_ws:
            await self.openai_ws.close()
        
        # Log session stats
        duration = time.time() - self.stats['session_start']
        avg_latency = sum(self.stats['total_latency']) / max(1, len(self.stats['total_latency']))
        
        logger.info(f"📊 {self.role} session {self.session_id} ended:")
        logger.info(f"   Duration: {duration:.1f}s")
        logger.info(f"   Transcripts: {self.stats['transcripts_processed']}")
        logger.info(f"   Responses: {self.stats['responses_generated']}")
        logger.info(f"   Audio chunks: {self.stats['audio_chunks_sent']}")
        logger.info(f"   Avg latency: {avg_latency:.3f}s")

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Enhanced WebSocket endpoint with role support"""
    session_id = str(uuid.uuid4())
    
    await websocket.accept()
    logger.info(f"🔗 WebSocket connected: {session_id}")
    
    # Create session with default role
    session = VoiceSession(session_id=session_id, websocket=websocket)
    active_sessions[session_id] = session
    
    try:
        # Connect to OpenAI
        await session.connect_to_openai()
        
        # Handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                message_type = data.get("type")
                
                if message_type == "set_role":
                    # Set the role for this session
                    role = data.get("role", "customer_service")
                    if role in ROLE_CONFIGS:
                        session.role = role
                        logger.info(f"Session {session_id} role set to: {role}")
                        await websocket.send_json({
                            "type": "status",
                            "message": f"تم تعيين الدور: {role}"
                        })
                
                elif message_type == "audio_chunk":
                    if not session.is_generating_audio:
                        audio_data = base64.b64decode(data["audio"])
                        await session.send_audio_chunk(audio_data)
                
                elif message_type == "stop_generation":
                    session.is_processing_response = False
                    session.is_generating_audio = False
                    await websocket.send_json({
                        "type": "status", 
                        "message": "تم إيقاف التوليد"
                    })
                
                elif message_type == "clear_conversation":
                    conversation_histories[session_id] = []
                    await websocket.send_json({
                        "type": "status", 
                        "message": "تم مسح المحادثة"
                    })
                
                elif message_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except json.JSONDecodeError:
                logger.error("Invalid JSON received")
                await websocket.send_json({
                    "type": "error",
                    "message": "رسالة غير صحيحة"
                })
            
    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": "حدث خطأ في الاتصال"
            })
        except:
            pass
    finally:
        # Cleanup
        if session_id in active_sessions:
            await active_sessions[session_id].close()
            del active_sessions[session_id]
        
        if session_id in conversation_histories:
            del conversation_histories[session_id]

# Health check endpoint
@app.get("/health")
async def health_check():
    """Comprehensive health check"""
    return {
        "status": "healthy",
        "architecture": "Enhanced AI Voice Platform",
        "services": {
            "openai": bool(openai_client),
            "elevenlabs": bool(elevenlabs_client),
            "overall_available": SERVICES_AVAILABLE
        },
        "active_sessions": len(active_sessions),
        "supported_roles": list(ROLE_CONFIGS.keys()),
        "features": [
            "✅ Role-based conversations",
            "✅ Real-time WebSocket communication",
            "✅ Advanced error handling",
            "✅ No-interruption audio streaming",
            "✅ Multi-language support (Arabic/English)",
            "✅ Performance monitoring"
        ],
        "environment": {
            "openai_key_configured": bool(OPENAI_API_KEY),
            "elevenlabs_key_configured": bool(ELEVENLABS_API_KEY),
            "voice_id": ELEVENLABS_VOICE_ID
        }
    }

# Root endpoint
@app.get("/")
async def root():
    """API information"""
    return {
        "message": "🚀 AI Voice Assistant Platform",
        "websocket_url": "ws://localhost:8000/ws",
        "supported_roles": {
            "police_call": "Emergency call operator",
            "police_interview": "Criminal investigator", 
            "customer_service": "Customer service representative"
        },
        "features": [
            "Role-based AI conversations",
            "Real-time audio transcription",
            "Streaming AI responses",
            "No-interruption voice flow",
            "Advanced error handling"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting Enhanced AI Voice Assistant Platform...")
    print("📡 WebSocket server: ws://localhost:8000/ws")
    print("🎭 Supported roles:")
    for role, config in ROLE_CONFIGS.items():
        print(f"   • {role}")
    print("🛡️ Enhanced error handling enabled")
    print("🔊 Audio streaming optimized")
    print("⚡ No-interruption conversation flow")
    
    # Environment check
    print("\n🔧 Environment check:")
    print(f"   OPENAI_API_KEY: {'✅ Set' if OPENAI_API_KEY else '❌ Missing'}")
    print(f"   ELEVENLABS_API_KEY: {'✅ Set' if ELEVENLABS_API_KEY else '❌ Missing'}")
    print(f"   ELEVENLABS_VOICE_ID: {ELEVENLABS_VOICE_ID}")
    
    if not SERVICES_AVAILABLE:
        print("⚠️  WARNING: Some AI services are not available!")
        print("   Check your .env file and API keys")
    else:
        print("✅ All AI services initialized successfully")
    
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True,
        log_level="info"
    )
