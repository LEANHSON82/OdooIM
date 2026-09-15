import { registry } from '@web/core/registry';

const TINY_MP4 = 'AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAAIZnJlZQ==';

const PNG_1PX =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk' +
    'YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==';

async function makeFile(name, type, base64) {
    const blob = await (await fetch(`data:${type};base64,${base64}`)).blob();
    return new File([blob], name, { type });
}

async function fillMultipleFiles(input, files) {
    const dataTransfer = new DataTransfer();
    for (const file of files) {
        dataTransfer.items.add(file);
    }
    input.files = dataTransfer.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
}

registry.category('web_tour.tours').add('im_multi_file_upload', {
    steps: () => [
        {
            content: 'Open the Add Content dialog',
            trigger: '.o_wslides_js_slide_upload',
            run: 'click',
        },
        {
            content: 'Pick the Image content type',
            trigger: 'a[data-slide-category=infographic]',
            run: 'click',
        },
        {
            content: 'Pick the source: upload from device',
            trigger: '#source_type_local_file',
            run: 'click',
        },
        {
            content: 'The file input must accept multiple files',
            trigger: 'input#upload[multiple]',
            run: () => {},
        },
        {
            content: 'Load 3 files at once - the step that used to break CE',
            trigger: 'input#upload',
            async run() {
                const input = document.getElementById('upload');
                const files = [
                    await makeFile('Lesson_1-Introduction.png', 'image/png', PNG_1PX),
                    await makeFile('Lesson_10-Summary.png', 'image/png', PNG_1PX),
                    await makeFile('Lesson_2-Process.png', 'image/png', PNG_1PX),
                ];
                await fillMultipleFiles(input, files);
            },
        },
        {
            content: 'It must report 3 files accepted, not an error',
            trigger: '.alert:contains("3 tệp"), .alert:contains("3 files")',
            run: () => {},
        },
    ],
});

registry.category('web_tour.tours').add('im_video_file_upload', {
    steps: () => [
        {
            content: 'Open the Add Content dialog',
            trigger: '.o_wslides_js_slide_upload',
            run: 'click',
        },
        {
            content: 'Pick the Video content type',
            trigger: 'a[data-slide-category=video]',
            run: 'click',
        },
        {
            content: 'Video must offer a source radio - CE only allows pasting a link',
            trigger: '#source_type_local_file',
            run: 'click',
        },
        {
            content: 'A file input must exist and accept multiple files',
            trigger: 'input#upload[multiple]',
            run: () => {},
        },
        {
            content: 'Load 2 video files at once',
            trigger: 'input#upload',
            async run() {
                const input = document.getElementById('upload');
                const files = [
                    await makeFile('Lesson_1-Introduction.mp4', 'video/mp4', TINY_MP4),
                    await makeFile('Lesson_2-Next_steps.mp4', 'video/mp4', TINY_MP4),
                ];
                await fillMultipleFiles(input, files);
            },
        },
        {
            content: 'It must report 2 files accepted, not an error',
            trigger: '.alert:contains("2 tệp"), .alert:contains("2 files")',
            run: () => {},
        },
        {
            content: 'Save and publish - only this step really creates the lesson and sends the file',
            trigger: 'footer.modal-footer button:contains("Publish"), footer.modal-footer button:contains("đăng")',
            run: 'click',
            expectUnloadPage: true,
        },
    ],
});

registry.category('web_tour.tours').add('im_video_too_big', {
    steps: () => [
        {
            content: 'Open the Add Content dialog',
            trigger: '.o_wslides_js_slide_upload',
            run: 'click',
        },
        {
            content: 'Pick the Video content type',
            trigger: 'a[data-slide-category=video]',
            run: 'click',
        },
        {
            content: 'Pick the source: upload from device',
            trigger: '#source_type_local_file',
            run: 'click',
        },
        {
            content: 'Load a file above the configured ceiling',
            trigger: 'input#upload',
            async run() {
                const input = document.getElementById('upload');
                const big = new File([new Uint8Array(2 * 1024 * 1024)],
                                     'Video_qua_lon.mp4', { type: 'video/mp4' });
                await fillMultipleFiles(input, [big]);
            },
        },
        {
            content: 'It must say the ceiling was exceeded, with the MB figure, not an opaque error',
            trigger: '.alert:contains("vượt trần")',
            run: () => {},
        },
    ],
});
