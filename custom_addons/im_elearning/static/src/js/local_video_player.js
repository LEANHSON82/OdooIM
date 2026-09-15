import { renderToElement } from '@web/core/utils/render';
import Fullscreen from '@website_slides/js/slides_course_fullscreen_player';

const COMPLETION_THRESHOLD_SECONDS = 30;

Fullscreen.include({

    _preprocessSlideData: function (slidesDataList) {
        const result = this._super.apply(this, arguments);
        result.forEach((slideData) => {
            if (slideData.category === 'video' && slideData.videoSourceType === 'local') {
                slideData.embedUrl = `/im_elearning/video/${encodeURIComponent(slideData.id)}`;
                slideData._autoSetDone = false;
            }
        });
        return result;
    },

    _renderSlide: async function () {
        const slide = this._slideValue;
        const isLocalVideo = slide
            && slide.category === 'video'
            && slide.videoSourceType === 'local'
            && !slide.isQuiz;

        if (!isLocalVideo) {
            return this._super.apply(this, arguments);
        }

        if (this._renderSlideRunning) {
            return;
        }
        this._renderSlideRunning = true;
        try {
            const $content = this.$('.o_wslides_fs_content');
            $content.empty();
            this.videoUrl = slide.embedUrl;
            $content.append(renderToElement('im_elearning.fullscreen.video.local', {
                widget: this,
            }));
            this._bindLocalVideoEvents($content.find('video')[0], slide);
        } finally {
            this._renderSlideRunning = false;
        }
    },

    _bindLocalVideoEvents: function (videoElement, slide) {
        if (!videoElement) {
            return;
        }

        videoElement.addEventListener('timeupdate', () => {
            const duration = videoElement.duration;
            if (!duration || !isFinite(duration)) {
                return;
            }
            const threshold = Math.max(0, duration - COMPLETION_THRESHOLD_SECONDS);
            if (videoElement.currentTime > threshold
                    && slide.isMember
                    && !slide.hasQuestion
                    && !slide.completed) {
                this.trigger_up('slide_mark_completed', slide);
            }
        });

        videoElement.addEventListener('ended', () => {
            if (slide.hasNext) {
                this.trigger_up('slide_go_next', slide);
            }
        });
    },
});
