#!/usr/bin/env node
import fs from "node:fs";
import { pathToFileURL } from "node:url";

const home = process.env.HOME;
if (!home) {
  throw new Error("HOME is not set");
}

const transportPath =
  process.env.CLI_WECHAT_BRIDGE_TRANSPORT ??
  `${home}/.npm-global/lib/node_modules/cli-wechat-bridge/dist/wechat/wechat-transport.js`;

const {
  WeChatTransport,
  classifyWechatTransportError,
  describeWechatTransportError,
  isWechatContextTokenStaleError,
} = await import(pathToFileURL(transportPath).href);

const logger = {
  log: (message) => console.error(`[cli-wechat-bridge] ${message}`),
  logError: (message) => console.error(`[cli-wechat-bridge:error] ${message}`),
};

const transport = new WeChatTransport(logger);
const command = process.argv[2] ?? "status";
const defaultContextMaxAgeSeconds = 24 * 60 * 60;

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks).toString("utf8");
}

async function sleep(milliseconds) {
  if (milliseconds > 0) {
    await new Promise((resolve) => setTimeout(resolve, milliseconds));
  }
}

async function readJSONStdin() {
  const input = await readStdin();
  if (!input.trim()) {
    throw new Error("Expected JSON on stdin");
  }
  return JSON.parse(input);
}

function describeError(error) {
  if (typeof describeWechatTransportError === "function") {
    return describeWechatTransportError(error);
  }
  return error instanceof Error ? error.message : String(error);
}

function retCode(error) {
  if (error && typeof error === "object" && "ret" in error && Number.isFinite(Number(error.ret))) {
    return Number(error.ret);
  }
  const match = describeError(error).match(/ret=(-?\d+)/);
  return match ? Number(match[1]) : null;
}

function classifyError(error) {
  const contextTokenRejected = typeof isWechatContextTokenStaleError === "function"
    ? isWechatContextTokenStaleError(error)
    : retCode(error) === -2;
  if (contextTokenRejected) {
    return { kind: "context-token-rejected", retryable: false, contextTokenRejected };
  }
  if (typeof classifyWechatTransportError === "function") {
    const classification = classifyWechatTransportError(error);
    return {
      kind: classification.kind ?? "unknown",
      retryable: classification.retryable === true,
      contextTokenRejected: false,
    };
  }
  return { kind: "unknown", retryable: false, contextTokenRejected: false };
}

function failureJSON(index, attemptCount, error, recipientId) {
  const classification = classifyError(error);
  let contextTokenCleared = false;
  if (classification.contextTokenRejected && recipientId) {
    contextTokenCleared = transport.clearCachedContextToken(recipientId);
  }
  return {
    index,
    attemptCount,
    reason: describeError(error),
    retCode: retCode(error),
    classification: classification.kind,
    retryable: classification.retryable,
    contextTokenRejected: classification.contextTokenRejected,
    contextTokenCleared,
  };
}

function normalizeBatchRequest(request) {
  const payloads = Array.isArray(request.payloads) ? request.payloads : [];
  return {
    recipientId: typeof request.recipientId === "string" && request.recipientId.trim()
      ? request.recipientId.trim()
      : undefined,
    delayMilliseconds: Math.max(0, Number(request.delayMilliseconds ?? 0) || 0),
    retryCount: Math.max(0, Number(request.retryCount ?? 0) || 0),
    payloads: payloads.map((payload, offset) => ({
      index: Number.isFinite(Number(payload.index)) ? Number(payload.index) : offset + 1,
      text: typeof payload.text === "string" ? payload.text : "",
    })).filter((payload) => payload.text.trim()),
  };
}

function normalizeFileRequest(request) {
  return {
    recipientId: typeof request.recipientId === "string" && request.recipientId.trim()
      ? request.recipientId.trim()
      : undefined,
    filePath: typeof request.filePath === "string" ? request.filePath.trim() : "",
    title: typeof request.title === "string" && request.title.trim()
      ? request.title.trim()
      : undefined,
  };
}

function nonEmptyString(value) {
  if (typeof value !== "string") {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function normalizeInboundMessage(message, offset) {
  const text = typeof message?.text === "string"
    ? message.text
    : typeof message?.content === "string"
      ? message.content
      : typeof message?.message === "string"
        ? message.message
        : "";
  const timestamp = message?.receivedAt ?? message?.timestamp ?? message?.createdAt ?? message?.time;
  let receivedAt = new Date().toISOString();
  if (typeof timestamp === "string" || typeof timestamp === "number") {
    const parsed = new Date(timestamp);
    if (Number.isFinite(parsed.getTime())) {
      receivedAt = parsed.toISOString();
    }
  }
  const recipientId = nonEmptyString(message?.recipientId) ??
    nonEmptyString(message?.conversationId) ??
    nonEmptyString(message?.chatId) ??
    nonEmptyString(message?.fromUserName) ??
    nonEmptyString(message?.from) ??
    nonEmptyString(message?.senderId);
  // The npm transport gives no message id; sender + create time is stable across polls.
  const createdAtMs = Number(message?.createdAtMs);
  const id = nonEmptyString(message?.id) ??
    nonEmptyString(message?.messageId) ??
    nonEmptyString(message?.msgId) ??
    nonEmptyString(message?.clientMsgId) ??
    nonEmptyString(message?.hash) ??
    (recipientId && createdAtMs > 0 ? `${recipientId}-${createdAtMs}` : undefined) ??
    `poll-${receivedAt}-${offset}`;
  return { id, recipientId, text, receivedAt };
}

async function pollMessages(timeoutMs) {
  const result = await transport.pollMessages({ timeoutMs });
  const messages = Array.isArray(result?.messages)
    ? result.messages.map(normalizeInboundMessage)
    : [];
  return {
    messages,
    messageCount: messages.length,
    ignoredBacklogCount: Number(result?.ignoredBacklogCount ?? 0) || 0,
  };
}

async function sendBatch(request) {
  const normalized = normalizeBatchRequest(request);
  if (normalized.payloads.length === 0) {
    throw new Error("notify-batch requires at least one non-empty payload");
  }
  const resolved = transport.resolveRecipient(normalized.recipientId);
  const accepted = [];
  let attemptedCount = 0;
  for (let payloadOffset = 0; payloadOffset < normalized.payloads.length; payloadOffset += 1) {
    const payload = normalized.payloads[payloadOffset];
    for (let attempt = 1; attempt <= normalized.retryCount + 1; attempt += 1) {
      attemptedCount += 1;
      try {
        await transport.sendTextWithContextToken(
          resolved.account,
          resolved.recipientId,
          payload.text,
          resolved.contextToken
        );
        accepted.push({
          index: payload.index,
          attemptCount: attempt,
          acceptedAt: new Date().toISOString(),
          bridgeResponse: `sent recipient=${resolved.recipientId}`,
        });
        break;
      } catch (error) {
        const failure = failureJSON(payload.index, attempt, error, resolved.recipientId);
        if (failure.contextTokenRejected || !failure.retryable || attempt > normalized.retryCount) {
          return {
            sent: false,
            recipient: resolved.recipientId,
            attemptedCount,
            accepted,
            failed: failure,
          };
        }
        await sleep(Math.min(10_000, 750 * attempt));
      }
    }
    if (payloadOffset + 1 < normalized.payloads.length) {
      await sleep(normalized.delayMilliseconds);
    }
  }
  return {
    sent: true,
    recipient: resolved.recipientId,
    attemptedCount,
    accepted,
  };
}

async function sendFileRequest(request, kind = "file") {
  const normalized = normalizeFileRequest(request);
  if (!normalized.filePath) {
    throw new Error(`send-${kind} requires filePath`);
  }
  const resolved = transport.resolveRecipient(normalized.recipientId);
  try {
    if (kind === "image") {
      // No caption: the transport would send it as an extra text message.
      await transport.sendImage(normalized.filePath, { recipientId: resolved.recipientId });
    } else {
      await transport.sendFile(normalized.filePath, {
        recipientId: resolved.recipientId,
        title: normalized.title,
      });
    }
    return {
      sent: true,
      recipient: resolved.recipientId,
      acceptedAt: new Date().toISOString(),
      bridgeResponse: `sent ${kind} recipient=${resolved.recipientId}`,
    };
  } catch (error) {
    return {
      sent: false,
      recipient: resolved.recipientId,
      failed: failureJSON(1, 1, error, resolved.recipientId),
    };
  }
}

function statusSummary() {
  const status = transport.getStatusText();
  const contextMatch = status.match(/^cached_context_count:\s*(\d+)/m);
  const cachedContextCount = Number(contextMatch?.[1] ?? 0);
  const credentialsPresent = /^credentials_present:\s*yes$/m.test(status);
  const contextCachePresent = /^context_cache_present:\s*yes$/m.test(status);
  const contextCacheFile = status.match(/^context_cache_file:\s*(.+)$/m)?.[1] ?? null;
  const maxContextAgeSeconds = maxContextAgeSecondsFromEnv();
  const contextCache = contextCacheMetadata(contextCacheFile);
  const contextCacheStale =
    cachedContextCount > 0 &&
    (contextCache.contextCacheAgeSeconds === null ||
      contextCache.contextCacheAgeSeconds > maxContextAgeSeconds);
  const sendableContextCache = cachedContextCount > 0
    ? contextCache
    : {
        ...contextCache,
        contextCacheAgeSeconds: null,
        lastInboundAt: null,
        lastInboundAgeSeconds: null,
      };

  return {
    ready: credentialsPresent && cachedContextCount > 0 && !contextCacheStale,
    credentialsPresent,
    contextCachePresent,
    cachedContextCount,
    contextCacheMaxAgeSeconds: maxContextAgeSeconds,
    contextCacheStale,
    contextCacheFresh: cachedContextCount > 0 && !contextCacheStale,
    ...sendableContextCache,
    savedAt: status.match(/^saved_at:\s*(.+)$/m)?.[1] ?? "(none)",
  };
}

function maxContextAgeSecondsFromEnv() {
  const value = Number(process.env.CLI_WECHAT_BRIDGE_CONTEXT_MAX_AGE_SECONDS ?? defaultContextMaxAgeSeconds);
  return Number.isFinite(value) && value > 0 ? value : defaultContextMaxAgeSeconds;
}

function contextCacheMetadata(filePath) {
  if (!filePath) {
    return {
      contextCacheModifiedAt: null,
      lastInboundAt: null,
      contextCacheAgeSeconds: null,
      lastInboundAgeSeconds: null,
    };
  }
  try {
    const stat = fs.statSync(filePath);
    const ageSeconds = Math.max(0, Math.round((Date.now() - stat.mtimeMs) / 1000));
    return {
      contextCacheModifiedAt: stat.mtime.toISOString(),
      lastInboundAt: stat.mtime.toISOString(),
      contextCacheAgeSeconds: ageSeconds,
      lastInboundAgeSeconds: ageSeconds,
    };
  } catch {
    return {
      contextCacheModifiedAt: null,
      lastInboundAt: null,
      contextCacheAgeSeconds: null,
      lastInboundAgeSeconds: null,
    };
  }
}

if (command === "status") {
  const summary = statusSummary();
  console.log(JSON.stringify(summary));
  if (!summary.ready) {
    process.exitCode = 2;
  }
} else if (command === "refresh-context") {
  const timeoutMs = Math.max(0, Number(process.argv[3] ?? 5000) || 5000);
  const before = statusSummary();
  const result = await pollMessages(timeoutMs);
  const after = statusSummary();
  console.log(JSON.stringify({
    refreshed: before.lastInboundAt !== after.lastInboundAt ||
      before.contextCacheModifiedAt !== after.contextCacheModifiedAt,
    messageCount: result.messages.length,
    ignoredBacklogCount: result.ignoredBacklogCount,
    beforeLastInboundAt: before.lastInboundAt,
    afterLastInboundAt: after.lastInboundAt,
    contextCacheFresh: after.contextCacheFresh === true,
    cachedContextCount: after.cachedContextCount,
  }));
} else if (command === "poll-messages" || command === "poll-keywords") {
  const timeoutMs = Math.max(0, Number(process.argv[3] ?? 5000) || 5000);
  const result = await pollMessages(timeoutMs);
  console.log(JSON.stringify(result));
} else if (command === "notify") {
  const useStdin = process.argv[3] === "--stdin";
  const message = useStdin ? await readStdin() : process.argv[3] ?? "";
  const recipientId = process.argv[4];
  try {
    const recipient = await transport.sendNotification(message, recipientId);
    console.log(JSON.stringify({ sent: true, recipient }));
  } catch (error) {
    const failure = failureJSON(1, 1, error, recipientId);
    console.log(JSON.stringify({ sent: false, failed: failure }));
    process.exitCode = 1;
  }
} else if (command === "notify-batch") {
  try {
    const request = await readJSONStdin();
    const result = await sendBatch(request);
    console.log(JSON.stringify(result));
    if (!result.sent) {
      process.exitCode = 1;
    }
  } catch (error) {
    console.log(JSON.stringify({
      sent: false,
      attemptedCount: 0,
      accepted: [],
      failed: failureJSON(1, 0, error, null),
    }));
    process.exitCode = 1;
  }
} else if (command === "send-file" || command === "send-image") {
  try {
    const request = await readJSONStdin();
    const result = await sendFileRequest(request, command === "send-image" ? "image" : "file");
    console.log(JSON.stringify(result));
    if (!result.sent) {
      process.exitCode = 1;
    }
  } catch (error) {
    console.log(JSON.stringify({
      sent: false,
      failed: failureJSON(1, 0, error, null),
    }));
    process.exitCode = 1;
  }
} else {
  throw new Error(`Unknown command: ${command}`);
}
