import { _t } from '@web/core/l10n/translation';

export const VIDEO_UPLOAD_ROUTE = '/im_elearning/video/upload';

/**
 * Send a lesson's video file as multipart, bypassing the base64 JSON-RPC path
 * and its 128 MiB request ceiling.
 *
 * Resolves to the server's JSON answer, `{ok, name, size}` on success or
 * `{ok: false, error}` otherwise, and never rejects: every failure mode is
 * turned into a message the caller can show as is.
 *
 * @param {number} slideId
 * @param {File} file
 * @param {(percent: number) => void} [onProgress]
 * @returns {Promise<{ok: boolean, name?: string, size?: number, error?: string}>}
 */
export function uploadVideoFile(slideId, file, onProgress) {
    return new Promise((resolve) => {
        const form = new FormData();
        form.append('slide_id', slideId);
        form.append('ufile', file);

        const xhr = new XMLHttpRequest();
        xhr.open('POST', VIDEO_UPLOAD_ROUTE, true);

        if (onProgress) {
            xhr.upload.addEventListener('progress', (event) => {
                if (event.lengthComputable) {
                    onProgress(Math.round((event.loaded / event.total) * 100));
                }
            });
        }

        xhr.addEventListener('load', () => {
            if (xhr.status === 413) {
                resolve({ ok: false, error: _t(
                    "Tệp vượt quá dung lượng máy chủ cho phép. Nén video lại, hoặc nhờ quản trị nâng tham số im_elearning.video_upload_limit_mb.") });
                return;
            }
            if (xhr.status !== 200) {
                resolve({ ok: false, error: _t("Máy chủ trả lỗi %s.", xhr.status) });
                return;
            }
            try {
                resolve(JSON.parse(xhr.responseText));
            } catch {
                resolve({ ok: false, error: _t("Máy chủ trả về dữ liệu không đọc được.") });
            }
        });

        xhr.addEventListener('error', () => {
            resolve({ ok: false, error: _t("Mất kết nối trong lúc tải tệp lên.") });
        });

        xhr.send(form);
    });
}
