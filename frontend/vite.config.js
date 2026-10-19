import {defineConfig} from 'vite';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig({plugins:[tailwindcss()],resolve:{dedupe:['react','react-dom']},build:{outDir:'../ui',emptyOutDir:true}});
