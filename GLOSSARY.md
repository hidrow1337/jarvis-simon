# Jarvis

A voice-driven dashboard over the user's Hermes agent: the user talks, Jarvis answers out loud.

## Language

### Conversation

**Turn**:
One exchange in a voice conversation: the user speaks, Jarvis hears it, Hermes answers, Jarvis says the answer.
_Avoid_: Round, cycle, request

**Hearing**:
Turning the user's recorded speech into text.
_Avoid_: Listening (that is the microphone being open), STT, recognition

**Speaking**:
Turning Jarvis's answer text into audio the user hears.
_Avoid_: TTS, voice, synthesis

**Voice**:
The particular sound of Jarvis when Speaking: who it sounds like.
_Avoid_: Speaker, TTS

### Models

**Hearing model**:
The local model that does Hearing (Parakeet).
_Avoid_: Audio LLM, speech model

**Speaking model**:
The local model that does Speaking.
_Avoid_: Audio LLM, voice model
