// static/js/main.js
document.addEventListener('DOMContentLoaded', function() {
    const splashScreen = document.getElementById('splashScreen');
    const mainContent = document.getElementById('mainContent');
    const storyPage = document.getElementById('storyPage');
    const generateButton = document.getElementById('generateButton');
    let currentStoryData = null;
    let currentPage = 0;

    // عرض شاشة البداية لمدة 3 ثواني
    setTimeout(() => {
        splashScreen.style.opacity = '0';
        splashScreen.style.transition = 'opacity 1s ease-out';
        
        setTimeout(() => {
            splashScreen.style.display = 'none';
            mainContent.style.display = 'block';
            mainContent.style.opacity = '0';
            
            // تأثير ظهور تدريجي للمحتوى الرئيسي
            requestAnimationFrame(() => {
                mainContent.style.transition = 'opacity 1s ease-in';
                mainContent.style.opacity = '1';
            });
        }, 1000);
    }, 3000);

    generateButton.addEventListener('click', async function() {
        const childName = document.getElementById('childName').value;
        const value = document.getElementById('value').value;

        if (!childName || !value) {
            alert('الرجاء إدخال جميع البيانات المطلوبة');
            return;
        }

        // إظهار شاشة التقدم
        mainContent.style.display = 'none';
        document.getElementById('progressScreen').style.display = 'block';

        try {
            const response = await fetch('/generate-story', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    child_name: childName,
                    value: value
                })
            });

            if (!response.ok) {
                throw new Error('حدث خطأ في إنشاء القصة');
            }

            currentStoryData = await response.json();
            
            // إخفاء شاشة التقدم وعرض صفحة القصة
            document.getElementById('progressScreen').style.display = 'none';
            storyPage.style.display = 'block';
            
            // تقسيم القصة إلى صفحات وعرضها
            const storyPages = splitStoryIntoPages(currentStoryData.story);
            currentStoryData.pages = storyPages;
            showPage(0);

        } catch (error) {
            console.error('Error:', error);
            alert('حدث خطأ أثناء إنشاء القصة');
            document.getElementById('progressScreen').style.display = 'none';
            mainContent.style.display = 'block';
        }
    });

    // التنقل بين الصفحات
    document.querySelector('.nav-button.prev').addEventListener('click', () => {
        if (currentPage > 0) {
            showPage(currentPage - 1);
        }
    });

    document.querySelector('.nav-button.next').addEventListener('click', () => {
        if (currentPage < currentStoryData.pages.length - 1) {
            showPage(currentPage + 1);
        }
    });

    function splitStoryIntoPages(story) {
        // تقسيم القصة إلى فقرات
        return story.split('\n\n').filter(page => page.trim());
    }

    function showPage(pageIndex) {
        currentPage = pageIndex;
        const storyContent = document.querySelector('.story-text');
        const storyImage = document.querySelector('.story-image');
        
        // تحديث النص
        storyContent.textContent = currentStoryData.pages[pageIndex];
        
        // تحديث الصورة
        if (currentStoryData.images[pageIndex]) {
            storyImage.style.backgroundImage = `url(data:image/jpeg;base64,${currentStoryData.images[pageIndex]})`;
        } else {
            storyImage.style.backgroundImage = 'none';
        }
        
        // تحديث مؤشر الصفحات
        document.querySelector('.current-page').textContent = pageIndex + 1;
        document.querySelector('.total-pages').textContent = currentStoryData.pages.length;
        
        // تحديث أزرار التنقل
        document.querySelector('.nav-button.prev').disabled = pageIndex === 0;
        document.querySelector('.nav-button.next').disabled = pageIndex === currentStoryData.pages.length - 1;
    }
});