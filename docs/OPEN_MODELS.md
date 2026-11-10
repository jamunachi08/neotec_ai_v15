# Open models in Neotec AI

## In short

Open-weight models (Qwen, gpt-oss, Gemma, Llama, Mistral, DeepSeek) are free to download. They are not inside
the app: a model is tens of gigabytes and needs a GPU, which Frappe Cloud does not have. You run the model on a
GPU server you control, and Neotec AI connects to it like any other provider. Data then stays on that
server, so an on-premises provider is allowed even in Strict residency mode.

Claude, Gemini and GPT-5-class models have no downloadable version; they are used through their paid APIs
(presets *Anthropic Claude*, *Google Gemini*, *OpenAI*).

## Three ways to use open models

| Option | Where data goes | Cost | Preset |
|---|---|---|---|
| Your GPU server with Ollama | Your server | Hardware or GPU rental | Ollama (self-hosted) |
| Your GPU server with vLLM | Your server | Hardware or GPU rental | vLLM (self-hosted) |
| NeotecAI appliance | Your server | Neotec subscription | NeotecAI On-Premises |
| A hosted router | Outside the Kingdom | Free models (`:free`) or pay per use | OpenRouter (open models, free and paid) |

Free hosted models are for trials only. They may log prompts or use them for training, their limits change
without notice, and they are always treated as External: sensitive DocTypes stay blocked in Guarded mode, and
the health check opens an issue while one is in use.

## Choosing a model

Press **Open models guide** on any Coworker Provider for the full catalogue. Starting points:

| GPU | Model | Why |
|---|---|---|
| 24 GB (e.g. RTX 4090, L4 x2) | Qwen3.6 27B or Qwen3.8 27B, 4-bit | Good Arabic, reliable tool calls, Apache 2.0 |
| 24 GB, many users | Qwen3.6 35B-A3B, 4-bit | Only 3B parameters work per token, so it is fast |
| 80 GB (A100 / H100) | gpt-oss 120B | Strong reasoning and tool use, Apache 2.0 |
| 8-16 GB | Qwen3.5 9B or gpt-oss 20B | Summaries, drafting, quality scoring; not multi-step playbooks |

Read the licence of any model before commercial use. Qwen 27B/35B and gpt-oss are Apache 2.0; Gemma, Llama and
the largest Qwen3.8 have their own licences.

## The tool-calling self-test

Coworkers work by calling tools. Many small models chat well and call tools badly. **Test tool calling** on the
provider runs four short checks: the right tool with the right argument, answering from the tool result,
working from an Arabic request, and not calling a tool when none is needed.

| Result | Meaning |
|---|---|
| Passed | All four checks passed. |
| Partial | Calls tools and uses results, but missed the Arabic or the restraint check. Usable; watch quality. |
| Failed | Playbooks refuse this provider, it is never used as a fallback, and the health check raises an issue. |

Changing the model or server URL resets the result to *Not tested*.

## Setting up the server

Use `deploy/gpu-server/` in this repository: a Docker Compose kit with Ollama or vLLM behind Caddy (TLS and an
API key). Follow its README. Then in Coworker Setup choose the matching preset, enter `https://<server>/v1` and
the key, press **Find models on this server**, save, and run **Test tool calling**.

A practical split: an open model on your own server as the default and for every coworker that touches
sensitive data, and a hosted frontier model (Claude, Gemini) as the provider override for the few playbooks
that need the strongest reasoning.

---

# النماذج المفتوحة في زميل نيوتك

النماذج مفتوحة الأوزان (Qwen وgpt-oss وGemma وLlama وMistral وDeepSeek) مجانية التنزيل، لكنها لا توضع داخل التطبيق؛ فحجم النموذج عشرات الغيغابايت ويحتاج إلى معالج رسومي، وهو غير متوفر في Frappe Cloud. يُشغَّل النموذج على خادم رسومي تملكه، ويتصل به زميل نيوتك كأي مزوّد آخر، فتبقى البيانات داخل المملكة ويُسمح به حتى في وضع الإقامة الصارم.

أما Claude وGemini فليس لها نسخ قابلة للتنزيل، وتُستخدم عبر واجهاتها المدفوعة.

- **خادمك مع Ollama أو vLLM:** البيانات على خادمك. استخدم الحزمة الموجودة في `deploy/gpu-server/`.
- **جهاز NeotecAI:** البيانات على خادمك مع دعم نيوتك.
- **موزّع مستضاف:** النماذج المنتهية بـ `:free` مجانية للتجربة فقط، وقد تُسجَّل الطلبات أو تُستخدم للتدريب، وتُعامَل دائماً كمزوّد خارجي.

**اختبار استدعاء الأدوات:** من صفحة المزوّد اضغط «Test tool calling». يُجري أربعة فحوص قصيرة، منها طلب باللغة العربية. النموذج الذي يفشل لا يُسمح له بتشغيل الأدلة التشغيلية ولا يُستخدم مزوّداً احتياطياً.

**نقطة بداية:** بطاقة 24 غيغابايت مع Qwen3.6 27B أو Qwen3.8 27B بدقة 4 بت، أو بطاقة 80 غيغابايت مع gpt-oss 120B. راجع ترخيص كل نموذج قبل الاستخدام التجاري.
