"use strict";
// Optional local MP4 header inspection, not a decoder or trusted server validation.
// Read at most 256 top-level headers and one <=2 MiB moov box; never read mdat.
window.VideoGuardMedia = Object.freeze({
  async inspect(file) {
    if (file.type !== "video/mp4") return {container: "WebM", note: "Native browser metadata is authoritative; MP4 inspection not applicable."};
    const fourcc = (v, p) => String.fromCharCode(...new Uint8Array(v.buffer, v.byteOffset+p, 4));
    let budget = 0;
    function box(v, start, end) {
      if (++budget > 1024 || start+8 > end) throw new Error("MP4 header bounds exceeded");
      let size = v.getUint32(start), header = 8;
      const type = fourcc(v,start+4);
      if (size === 1) {
        if (start+16 > end) throw new Error("Truncated extended MP4 box");
        size = Number(v.getBigUint64(start+8)); header = 16;
      }
      if (size === 0) size = end-start;
      if (!Number.isSafeInteger(size) || size < header || start+size > end) throw new Error("Invalid MP4 box size");
      return {type, start, data: start+header, end: start+size};
    }
    function children(v,start,end) {
      const found=[];
      while (start < end) { const b=box(v,start,end); found.push(b); start=b.end; }
      return found;
    }
    function find(v,parent,type) { return children(v,parent.data,parent.end).find(b=>b.type===type); }
    function tracks(v, root) {
      return children(v,root.data,root.end).filter(b=>b.type==='trak').map(trak=>{
        const track={}, tkhd=find(v,trak,'tkhd'), mdia=find(v,trak,'mdia');
        if (tkhd && tkhd.end-tkhd.data >= 84) {
          track.trackWidth=v.getUint32(tkhd.end-8)/65536;
          track.trackHeight=v.getUint32(tkhd.end-4)/65536;
          const matrix=tkhd.data+(v.getUint8(tkhd.data)===1?52:40);
          if (matrix+20 <= tkhd.end-8) {
            const a=v.getInt32(matrix)/65536, b=v.getInt32(matrix+4)/65536;
            track.rotationDegrees=Math.round(Math.atan2(b,a)*180/Math.PI);
          }
        }
        if (!mdia) return track;
        const hdlr=find(v,mdia,'hdlr'), minf=find(v,mdia,'minf');
        if (hdlr && hdlr.data+12<=hdlr.end) track.handler=fourcc(v,hdlr.data+8);
        const stbl=minf && find(v,minf,'stbl'), stsd=stbl && find(v,stbl,'stsd');
        if (track.handler==='vide' && stsd && stsd.data+8 <= stsd.end) {
          const entry=children(v,stsd.data+8,stsd.end)[0];
          if (entry) {
            track.codec=entry.type;
            if (entry.start+36 <= entry.end) {
              track.codedWidth=v.getUint16(entry.start+32); track.codedHeight=v.getUint16(entry.start+34);
            }
          }
        }
        return track;
      });
    }
    try {
      for (let offset=0, count=0; offset<file.size && count<256; count++) {
        const v=new DataView(await file.slice(offset,Math.min(file.size,offset+16)).arrayBuffer());
        if (v.byteLength<8) throw new Error("Truncated MP4 header");
        const type=fourcc(v,4);
        let size=v.getUint32(0), header=8;
        if (size===1) { if(v.byteLength<16) throw new Error("Truncated MP4 box"); size=Number(v.getBigUint64(8)); header=16; }
        if(size===0) size=file.size-offset;
        if(!Number.isSafeInteger(size)||size<header||offset+size>file.size) throw new Error("Invalid MP4 box size");
        if(type==='moov') {
          if(size>2*1024*1024) return {container:"MP4", note:"moov exceeds 2 MiB inspection limit"};
          const metadata=new DataView(await file.slice(offset,offset+size).arrayBuffer());
          return {container:"MP4", tracks:tracks(metadata,box(metadata,0,metadata.byteLength))};
        }
        offset+=size;
      }
      return {container:"MP4", note:"No moov found within bounded header scan"};
    } catch (err) { return {container:"MP4", note:err.message}; }
  }
});
