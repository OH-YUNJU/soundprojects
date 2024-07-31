import React, { useState } from "react";
import './Notice.css';
import Editor from '../components/Editor';
import { Link, useNavigate } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import Header from '../components/Header';
import Footer from '../components/Footer';
import Backspace from '../components/Backspace';

<link rel="manifest" href="/manifest.json" />

const REACT_APP_FASTAPI = process.env.REACT_APP_FASTAPI;

const NoticeWrite = () => {
    const [isSidebarOpen, setSidebarOpen] = useState(false);
    const [title, setTitle] = useState('');
    const [content, setContent] = useState('');
    const navigate = useNavigate();

    const toggleSidebar = () => {
        setSidebarOpen(!isSidebarOpen);
    };

    function onTitleChange(e) {
        setTitle(e.target.value);
    }

    function stripHtmlAndExtractImage(html) {
        let tmp = document.createElement("DIV");
        tmp.innerHTML = html;
        
        const imgTag = tmp.querySelector('img');
        let imageData = null;
        if (imgTag) {
            const src = imgTag.getAttribute('src');
            imageData = src && src.startsWith('data:image') ? src : null;
            imgTag.remove();
        }
    
        const text = tmp.innerHTML;
        return { text, imageData };
    }

    async function resizeAndCompressImage(base64Str, maxWidth = 800, maxHeight = 600) {
        return new Promise((resolve) => {
            let img = new Image();
            img.src = base64Str;
            img.onload = () => {
                let canvas = document.createElement('canvas');
                let width = img.width;
                let height = img.height;

                if (width > height) {
                    if (width > maxWidth) {
                        height *= maxWidth / width;
                        width = maxWidth;
                    }
                } else {
                    if (height > maxHeight) {
                        width *= maxHeight / height;
                        height = maxHeight;
                    }
                }

                canvas.width = width;
                canvas.height = height;

                let ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, width, height);

                resolve(canvas.toDataURL('image/png', 0.7)); 
            };
        });
    }

    const saveNotice = async () => {
        try {
            const { text, imageData } = stripHtmlAndExtractImage(content);
            
            let processedImageData = imageData;
            if (imageData && typeof imageData === 'string' && imageData.startsWith('data:image')) {
                processedImageData = await resizeAndCompressImage(imageData);
            }

            const response = await fetch(`${REACT_APP_FASTAPI}/noticeInsert`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    title: title,
                    content: text,
                    file: processedImageData && typeof processedImageData === 'string' 
                    ? processedImageData.split(',')[1] 
                    : null 
                }),
            });

            if (!response.ok) {
                throw new Error('Network response was not ok');
            }

            const result = await response.json();
            if (result.notice_no) {
                navigate(`/NoticeContent/${result.notice_no}`);
            } else {
                throw new Error('No notice number returned');
            }
        } catch (error) {
            console.error('Error saving notice:', error);
            alert('게시글 저장 중 오류가 발생했습니다.');
        }
    }

    const handleLinkClick = (e) => {
        e.preventDefault();
        if (window.confirm('입력한 내용이 저장되지 않을 수 있습니다. 정말로 나가시겠습니까?')) {
            navigate('/NoticeList');
        }
    };

    return (
        <div className={`container ${isSidebarOpen ? 'blur' : ''}`}>
            <Backspace />
            <Header toggleSidebar={toggleSidebar} />
            <Sidebar isOpen={isSidebarOpen} onClose={toggleSidebar} />
        <main style= {{ padding: '0px' }}>
            <div className="notice-container">
                <div className="notice-editor">
                    <div className='notice-top'>
                        <Link to = "#" onClick={handleLinkClick} as="div" className="arrow">{'<'}</Link>
                        <div className='title'>글쓰기</div>
                    </div>
                    <div className='notice-body'>
                        <input type="text" maxLength="100" placeholder="제목" className="input-title" onChange={onTitleChange}/>
                        <Editor value={content} onChange={setContent} />
                    </div>
                    <div className='notice-bottom'>
                        <button className='button' onClick={saveNotice}>저장</button>
                    </div>
                </div>
            </div>
        </main>
        <Footer />
        </div>
    );
};

export default NoticeWrite;