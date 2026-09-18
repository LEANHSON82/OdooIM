import { patch } from '@web/core/utils/patch';
import { getDataURLFromFile, redirect } from '@web/core/utils/urls';
import { rpc } from '@web/core/network/rpc';
import { _t } from '@web/core/l10n/translation';

import { SlideUploadCategory } from '@website_slides/js/public/components/slide_upload_dialog/slide_upload_category';
import { SlideUploadDialog } from '@website_slides/js/public/components/slide_upload_dialog/slide_upload_dialog';
import { SlideUploadSourceTypes } from '@website_slides/js/public/components/slide_upload_dialog/slide_upload_source_types';

import { uploadVideoFile } from '@im_elearning/js/video_upload';

// CE hard-codes this browser-side ceiling for images and PDFs.
const MAX_FILE_SIZE = 25 * 1024 * 1024;
const VIDEO_EXTENSIONS = 'video/mp4,video/webm,video/ogg,video/quicktime,.mp4,.webm,.ogv,.mov,.m4v';

// CE blocks multi-file video upload in four places and this file lifts all
// four: the accepted file types below, onChangeFileInput taking only the
// first file, the 25 MB browser cap, and _formValidateGetValues forcing
// every video to be an external link.
SlideUploadCategory.sourceSettings.video = {
    ...SlideUploadCategory.sourceSettings.video,
    sourceTypeLabel: _t("Video Source"),
    selectFileLabel: _t("Chọn tệp video"),
    acceptedFiles: VIDEO_EXTENSIONS,
    externalLabel: _t("Dán liên kết YouTube / Vimeo / Google Drive"),
};

SlideUploadSourceTypes.props.attributes.shape.externalLabel = {
    type: String,
    optional: true,
};

// A file name becomes the lesson title: drop the extension, tidy separators.
function titleFromFilename(filename) {
    const stem = filename.replace(/\.[^.]+$/, '');
    return stem.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim() || filename;
}

// Natural order, so lesson 2 sorts before lesson 10.
function naturalCompare(a, b) {
    return a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });
}

patch(SlideUploadCategory.prototype, {

    get imIsVideoUpload() {
        return this.props.slideCategory === 'video' && this.state.form.isLocalSource;
    },

    // Keep every selected file. CE reads only the first one; the rest go to
    // imVideoFiles, or to imExtraFiles as base64 images and PDFs.
    async onChangeFileInput(ev) {
        const all = [...(ev.target.files || [])];
        this.imExtraFiles = [];
        this.imVideoFiles = [];
        this.imRejectedFiles = [];

        if (this.imIsVideoUpload) {
            return this._imHandleVideoFiles(all);
        }

        const extras = all.slice(1).sort(naturalCompare);
        const result = await super.onChangeFileInput(ev);

        if (!this.file.name) {
            return result;
        }

        for (const file of extras) {
            const isImage = /^image\/.*/.test(file.type);
            const isPdf = file.type === 'application/pdf';
            if (!isImage && !isPdf) {
                this.imRejectedFiles.push(`${file.name} (không phải PDF hoặc ảnh)`);
                continue;
            }
            if (file.size > MAX_FILE_SIZE) {
                this.imRejectedFiles.push(`${file.name} (vượt 25 MB)`);
                continue;
            }
            const dataURL = await getDataURLFromFile(file);
            this.imExtraFiles.push({
                name: file.name,
                type: file.type,
                data: dataURL.split(',', 2)[1],
            });
        }
        this._imAnnounce(this.imExtraFiles.length + 1);
        return result;
    },

    // Sort and validate the chosen videos against the server-side ceiling.
    async _imHandleVideoFiles(files) {
        this._alertRemove();

        // Ask the server for its limit; unreachable means no browser check.
        let limitMb = 0;
        try {
            const info = await rpc('/im_elearning/video/upload_limit', {});
            limitMb = info.limit_mb || 0;
        } catch {
            limitMb = 0;
        }

        const accepted = [];
        for (const file of files) {
            if (!/^video\//.test(file.type) && !/\.(mp4|webm|ogv|mov|m4v)$/i.test(file.name)) {
                this.imRejectedFiles.push(`${file.name} (không phải tệp video)`);
                continue;
            }
            if (limitMb && file.size > limitMb * 1024 * 1024) {
                this.imRejectedFiles.push(
                    `${file.name} (${Math.round(file.size / 1024 / 1024)} MB, vượt trần ${limitMb} MB)`);
                continue;
            }
            accepted.push(file);
        }
        this.imVideoFiles = accepted.sort(naturalCompare);

        if (!this.imVideoFiles.length) {
            this._alertDisplay(this.imRejectedFiles.length
                ? _t("Không tải được: %s", this.imRejectedFiles.join(', '))
                : _t("Không có tệp video hợp lệ nào được chọn."));
            return;
        }
        if (!this.state.form.slideName) {
            this.state.form.slideName = titleFromFilename(this.imVideoFiles[0].name);
        }
        this.file.name = this.imVideoFiles[0].name;
        this.file.type = this.imVideoFiles[0].type;
        this._imAnnounce(this.imVideoFiles.length);
    },

    // Tell the user what was skipped, or how many lessons will be created.
    _imAnnounce(total) {
        if (this.imRejectedFiles.length) {
            this._alertDisplay(_t(
                "Bỏ qua %s tệp: %s",
                this.imRejectedFiles.length, this.imRejectedFiles.join(', ')));
        } else if (total > 1) {
            this._alertDisplay(_t(
                "Đã chọn %s tệp. Mỗi tệp sẽ thành một bài giảng, tiêu đề lấy theo tên tệp.",
                total), 'alert-info');
        }
    },

    // CE forces source_type to external for every video; undo that when the
    // user picked real files.
    async _formValidateGetValues(forcePublished) {
        const values = await super._formValidateGetValues(forcePublished);
        if (this.imVideoFiles?.length) {
            values.source_type = 'local_file';
            delete values.video_url;
        }
        return values;
    },

    // Turn one form into a batch of lesson values, one entry per file.
    // The first video keeps the typed title, the others take their filename.
    async onClickFormSubmit(forcePublished) {
        const hasVideos = this.imVideoFiles?.length;
        const hasExtras = this.imExtraFiles?.length;
        if (!hasVideos && !hasExtras) {
            return super.onClickFormSubmit(forcePublished);
        }
        if (!this._formValidate()) {
            return;
        }

        const base = await this._formValidateGetValues(forcePublished);
        const batch = [];

        if (hasVideos) {
            this.imVideoFiles.forEach((file, index) => {
                batch.push({
                    ...base,
                    name: index === 0 && base.name
                        ? base.name
                        : titleFromFilename(file.name),
                    _imVideoFile: file,
                });
            });
        } else {
            batch.push(base);
            for (const file of this.imExtraFiles) {
                batch.push({
                    ...base,
                    name: titleFromFilename(file.name),
                    binary_content: file.data,
                    slide_category: file.type === 'application/pdf' ? 'document' : 'infographic',
                    image_1920: undefined,
                });
            }
        }
        this.props.upload(batch, this.props.slideCategory);
    },
});

patch(SlideUploadDialog.prototype, {

    // Create the lessons one by one, then send each video separately.
    //
    // The video never travels with the create call: /slides/add_slide is
    // JSON-RPC, so a base64 payload would hit the 128 MiB request cap.
    async uploadSlide(formValues, previousPage) {
        // A plain object means the stock single-file flow.
        if (!Array.isArray(formValues)) {
            return super.uploadSlide(formValues, previousPage);
        }

        this.state.page = 'upload';
        this.state.size = 'md';

        // One failure must not lose the lessons that did work, so errors are
        // collected and the user lands on the last lesson created.
        let lastUrl = null;
        const failed = [];
        for (const entry of formValues) {
            const { _imVideoFile: videoFile, ...values } = entry;

            const data = await rpc('/slides/add_slide', values);
            if (data.error) {
                failed.push(`${values.name}: ${data.error}`);
                continue;
            }
            if (videoFile) {
                const uploaded = await uploadVideoFile(data.slide_id, videoFile);
                if (!uploaded.ok) {
                    failed.push(_t(
                        "%(name)s: %(error)s Bài giảng đã được tạo nhưng chưa có video.",
                        { name: values.name, error: uploaded.error }));
                    continue;
                }
            }
            lastUrl = data.url;
        }

        if (!lastUrl) {
            this.state.page = previousPage;
            this.state.size = 'lg';
            this.state.alertMsg = failed.join(' · ');
            return;
        }
        if (failed.length) {
            console.warn('im_elearning: không tạo được một số bài giảng', failed);
        }
        redirect(lastUrl);
    },
});
