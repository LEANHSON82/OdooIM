import { registry } from '@web/core/registry';
import { standardFieldProps } from '@web/views/fields/standard_field_props';
import { useService } from '@web/core/utils/hooks';
import { _t } from '@web/core/l10n/translation';
import { Component, useState, useRef } from '@odoo/owl';

import { uploadVideoFile } from '@im_elearning/js/video_upload';

/**
 * Backend field widget uploading a lesson video over multipart.
 *
 * The stock binary widget sends base64 inside one JSON-RPC call, which hits
 * the 128 MiB request cap and inflates the file by a third.
 */
export class VideoUploadField extends Component {
    static template = 'im_elearning.VideoUploadField';
    static props = { ...standardFieldProps };

    setup() {
        this.notification = useService('notification');
        this.fileInput = useRef('fileInput');
        this.state = useState({
            uploading: false,
            progress: 0,
            uploadedName: '',
        });
    }

    get hasVideo() {
        return !!this.props.record.data[this.props.name];
    }

    get slideId() {
        return this.props.record.resId;
    }

    get sizeLabel() {
        const raw = this.props.record.data[this.props.name];
        if (!raw || typeof raw !== 'string') {
            return '';
        }
        return raw.length < 40 ? raw : '';
    }

    onSelectFile() {
        // The upload route needs the lesson id, so the record must exist.
        if (!this.slideId) {
            this.notification.add(
                _t("Lưu bài giảng trước đã, rồi mới tải video lên."),
                { type: 'warning' }
            );
            return;
        }
        this.fileInput.el.click();
    }

    async onFileChange(ev) {
        const file = ev.target.files[0];
        if (!file) {
            return;
        }
        await this.upload(file);
        ev.target.value = '';
    }

    // Upload with a progress bar, then reload so the field shows the file.
    async upload(file) {
        this.state.uploading = true;
        this.state.progress = 0;
        const result = await uploadVideoFile(this.slideId, file, (percent) => {
            this.state.progress = percent;
        });
        this.state.uploading = false;

        if (!result.ok) {
            this.notification.add(
                result.error || _t("Tải lên thất bại."),
                { type: 'danger', sticky: true }
            );
            return;
        }
        this.state.uploadedName = result.name;
        this.notification.add(_t("Đã tải lên %s.", result.name), { type: 'success' });
        await this.props.record.load();
    }
}

registry.category('fields').add('im_video_upload', {
    component: VideoUploadField,
    supportedTypes: ['binary'],
});
