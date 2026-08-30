/**
 * API 调用封装
 */
const API_BASE = "http://localhost:8001";

/**
 * 获取 OSS 预签名上传 URL
 */
export async function getOssPresignUrl(filename: string): Promise<{ uploadUrl: string; accessUrl: string; contentType: string }> {
    const response = await fetch(`${API_BASE}/api/v1/oss/presign?filename=${filename}`);
    if (!response.ok) {
        throw new Error("获取上传 URL 失败");
    }
    const data = await response.json();
    return {
        uploadUrl: data.uploadUrl.trim().replace(/^["']|["']$/g, ''),
        accessUrl: data.accessUrl.trim().replace(/^["']|["']$/g, ''),
        contentType: data.contentType
    };
}

/**
 * 上传图片到 OSS
 */
export async function uploadImageToOss(file: File): Promise<string> {
    // 生成文件名
    const ext = file.name.split(".").pop() || "jpg";
    const filename = `${Date.now()}.${ext}`;

    // 获取预签名 URL
    const { uploadUrl, accessUrl, contentType } = await getOssPresignUrl(filename);

    // 上传图片
    const response = await fetch(uploadUrl, {
        method: "PUT",
        body: file,
        headers: {
            "Content-Type": contentType,
        },
    });

    if (!response.ok) {
        throw new Error(`图片上传失败: ${response.status}`);
    }

    // 返回可访问的图片路径
    return accessUrl;
}

/**
 * 流式聊天
 */
export async function streamChat(
    message: string,
    onChunk: (chunk: string) => void,
    image_url?: string,
    onError?: (error: Error) => void,
    onComplete?: () => void,
    threadId?: string
): Promise<void> {
    try {
        const url = new URL(`${API_BASE}/api/v1/chat/stream`);

        const response = await fetch(url.toString(), {
            method: "POST",
            body: JSON.stringify({
                message,
                image_url: image_url,
                thread_id: threadId,
            }),
            headers: {
                "Content-Type": "application/json",
            },
        });

        if (!response.ok) {
            throw new Error("请求失败");
        }

        const reader = response.body?.getReader();
        if (!reader) {
            throw new Error("无法读取响应流");
        }

        const decoder = new TextDecoder();

        while (true) {
            const {done, value} = await reader.read();
            if (done) {
                onComplete?.();
                break;
            }

            const chunk = decoder.decode(value, {stream: true});
            onChunk(chunk);
        }
    } catch (error) {
        onError?.(error as Error);
    }
}

/**
 * 获取聊天历史
 */
export async function getChatHistory(threadId: string): Promise<{ role: string; content: string }[]> {
    const response = await fetch(`${API_BASE}/api/v1/chat/messages?thread_id=${threadId}`);
    if (!response.ok) {
        throw new Error("获取历史消息失败");
    }
    const data = await response.json();
    return data.messages;
}

/**
 * 清空聊天历史
 */
export async function clearChatHistory(threadId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/api/v1/chat/messages?thread_id=${threadId}`, {
        method: "DELETE",
    });
    if (!response.ok) {
        throw new Error("清空历史消息失败");
    }
}