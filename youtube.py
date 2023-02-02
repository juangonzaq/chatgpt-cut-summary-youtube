# Rest framework
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.decorators import action

# Models
from wapp.schedule.models import Schedule

# Libraries
import moviepy.editor as mp
from moviepy.editor import concatenate_videoclips

from pytube import YouTube
import xml.etree.ElementTree as ET
import io, re, os, random, math
from slugify import slugify
import openai


class CutViewSet(viewsets.ModelViewSet):
    permission_classes = []
    authentication_classes = []
    queryset = Schedule.objects.all()
    
    @action(detail=False, methods=['post'])
    def run(self, request):
        # Donwload video
        video_path = self.donwload_video(request.data['url'])

        # Get captions
        caption = self.get_captions(request.data['url'])

        # Set captions format
        result = self.set_captions_format(caption)

        data = self.select_fragments_openai(result, video_path)
 
        # Cut video
        self.cut_video(data, video_path)

        return Response({}, status=status.HTTP_200_OK)

    def donwload_video(self, url):
        yt = YouTube(url)
        slugified_title = slugify(yt.title)

        video = yt.streams.filter(res='720p', mime_type='video/mp4').first()
        video.download(filename='{0}.mp4'.format(slugified_title))
        return "{0}.mp4".format(slugified_title)

    def get_captions(self, url):
        yt = YouTube(url)
        caption = yt.captions.get_by_language_code('a.es')
        return caption.xml_captions
    
    def set_captions_format(self, captions):
        caption_file = io.StringIO(captions)
        tree = ET.parse(caption_file)
        root = tree.getroot()

        caption_time = {}
        for p in root.findall('.//p'):
            text = " ".join(s.text for s in p.findall('.//s'))
            time = p.get('t')
            caption_time[time] = text
        
        caption_time = {k: v for k, v in caption_time.items() if v}
        
        result = []
        counter = 1
        temp_dict = {}

        for key, value in caption_time.items():
            if counter == 1:
                temp_dict["inicio"] = key
            if counter % 40 == 0 or counter == len(caption_time):
                temp_dict["fin"] = key
                temp_dict["contenido"] = [v for k, v in caption_time.items() if int(k) >= int(temp_dict["inicio"]) and int(k) <= int(key)]
                result.append(temp_dict)
                temp_dict = {}
                temp_dict["inicio"] = key
            counter += 1
        return result

    def select_fragments_openai(self, result, title):
        data = []
        for fragment in result:
            openai.api_key = "¡¡¡HERE-KEY-CHATGPT!!!"
            response = openai.Completion.create(
                model="text-davinci-003",
                prompt="{0}. ¿tiene que ver con este titulo: {1}, puedes responderme con un un YES o NOT".format(fragment, title),
                max_tokens=1024,
                temperature=0.3,
                top_p=0.9,
            )
            
            string = re.sub(r'\n', '', response.choices[0].text)
            string = re.sub(r'[^a-zA-Z0-9]', '', string)
            string = string.replace("?","")
            
            if string == 'YES' or string == 'yes' or string == 'Yes':
                data.append(fragment)

        return data

    def cut_video(self, result, path):
        video = mp.VideoFileClip(path)
        fragments = []
        video_files = []

        for cut_video in result:
            fragment = video.subclip(int(cut_video["inicio"])/1000, int(cut_video["fin"])/1000)
            file_name = "fragment{}.mp4".format(cut_video["inicio"])
            fragment.write_videofile(file_name, audio=True, codec='libx264', audio_codec='aac', temp_audiofile='temp-audio.m4a', remove_temp=True, verbose=False, logger=None)
            fragments.append(fragment)
            video_files.append(file_name)

        final_video = concatenate_videoclips(fragments)
        final_video = final_video.resize(width=final_video.w*9/16)
        final_video.write_videofile("final_video.mp4", codec='libx264', audio_codec='aac', temp_audiofile='temp-audio.m4a', remove_temp=True, verbose=False, logger=None)
        total_duration = final_video.duration
        
        for i in range(0, math.ceil(total_duration), 60):
            segment = final_video.subclip(i, i+60)
            segment_file = f"final_video_{i}.mp4"
            segment.write_videofile(segment_file, codec='libx264', audio_codec='aac', temp_audiofile='temp-audio.m4a', remove_temp=True, verbose=False, logger=None)
