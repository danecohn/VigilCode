/* SPDX-License-Identifier: GPL-3.0-or-later
 * VigilCode native support. No Python runtime or interpreter is linked. */
#ifndef VIGILCODE_RUNTIME_H
#define VIGILCODE_RUNTIME_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <math.h>
#include <limits.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

/* Resource limits. The compiler passes these with -D; 0 means no limit. */
#ifndef VT_MAX_STEPS
#define VT_MAX_STEPS 0
#endif
#ifndef VT_MAX_DEPTH
#define VT_MAX_DEPTH 2000
#endif
#ifndef VT_MAX_MEMORY
#define VT_MAX_MEMORY 1073741824
#endif
#ifndef VT_MAX_OUTPUT
#define VT_MAX_OUTPUT 0
#endif

static int vt_argc;
static char **vt_argv;
static uint64_t vt_steps=0, vt_output=0, vt_depth=0;
static size_t vt_memory=0;
typedef struct vt_allocation { struct vt_allocation *next; max_align_t align; } vt_allocation;
static vt_allocation *vt_allocations=NULL;
static inline void vt_cleanup(void) { while(vt_allocations) { vt_allocation *next=vt_allocations->next; free(vt_allocations); vt_allocations=next; } }
static inline void vt_fail(const char *where, const char *message) {
    fflush(stdout); fprintf(stderr,"%s: VigilCode: %s\n",where,message); exit(1);
}
static inline void vt_obligation(const char *where, const char *kind, const char *message) {
    fflush(stdout); fprintf(stderr,"%s: %s not satisfied: %s\n",where,kind,message); exit(1);
}
static inline bool vt_valid_utf8(const unsigned char *s, size_t n) {
    size_t i=0;
    while(i<n) {
        unsigned c=s[i]; size_t extra; uint32_t cp;
        if(c<0x80) { i++; continue; }
        else if(c>=0xC2 && c<=0xDF) { extra=1; cp=c&0x1F; }
        else if(c>=0xE0 && c<=0xEF) { extra=2; cp=c&0x0F; }
        else if(c>=0xF0 && c<=0xF4) { extra=3; cp=c&0x07; }
        else return false;
        for(size_t k=1;k<=extra;k++) { if(i+k>=n || (s[i+k]&0xC0)!=0x80) return false; cp=(cp<<6)|(s[i+k]&0x3F); }
        if((extra==2 && (cp<0x800 || (cp>=0xD800 && cp<=0xDFFF))) || (extra==3 && (cp<0x10000 || cp>0x10FFFF))) return false;
        i+=extra+1;
    }
    return true;
}
/* Write bytes exactly as given (UTF-8, \n line endings) on every platform. */
static inline void vt_init(int argc, char **argv) {
    vt_argc=argc; vt_argv=argv;
#ifdef _WIN32
    _setmode(_fileno(stdout), _O_BINARY); _setmode(_fileno(stderr), _O_BINARY); _setmode(_fileno(stdin), _O_BINARY);
#endif
}
static inline void vt_step(const char *where) { if(VT_MAX_STEPS && ++vt_steps>(uint64_t)VT_MAX_STEPS) vt_fail(where,"Execution limit reached (work calls and loop steps)."); }
/* Call depth is bounded well inside a 1 MiB stack (the smallest default, on Windows). */
static inline void vt_enter(const char *where) { if(++vt_depth>(uint64_t)VT_MAX_DEPTH) vt_fail(where,"Call depth limit reached (nested work calls)."); }
static inline void *vt_alloc(size_t n, const char *where) {
    if(n>(size_t)VT_MAX_MEMORY || vt_memory>(size_t)VT_MAX_MEMORY-n) vt_fail(where,"Memory limit reached.");
    if(n>SIZE_MAX-sizeof(vt_allocation)) vt_fail(where,"Unable to allocate memory.");
    vt_allocation *block=malloc(sizeof(*block)+n);
    if(!block) vt_fail(where,"Unable to allocate memory.");
    block->next=vt_allocations; vt_allocations=block; vt_memory+=n;
    return (void *)(block+1);
}
static inline void vt_write(const char *text) {
    size_t n=strlen(text);
    if(VT_MAX_OUTPUT && (n>(uint64_t)VT_MAX_OUTPUT || vt_output>(uint64_t)VT_MAX_OUTPUT-n)) vt_fail("output","Output limit reached.");
    vt_output+=n; fputs(text,stdout);
}
static inline void vt_say_text(const char *value) { vt_write(value); vt_write("\n"); }
static inline const char *vt_text_copy(const char *s, size_t n, const char *where) { char *t=vt_alloc(n+1,where); memcpy(t,s,n); t[n]=0; return t; }
static inline const char *vt_int_text(int64_t value,const char *where) { char t[32]; snprintf(t,sizeof t,"%" PRId64,value); return vt_text_copy(t,strlen(t),where); }
static inline const char *vt_real_text(double value,const char *where) { char t[40]; snprintf(t,sizeof t,"%.17g",value); return vt_text_copy(t,strlen(t),where); }
static inline const char *vt_bool_text(bool value) { return value?"true":"false"; }
static inline void vt_say_int(int64_t value) { char text[32]; snprintf(text,sizeof text,"%" PRId64,value); vt_say_text(text); }
static inline void vt_say_real(double value) { char text[40]; snprintf(text,sizeof text,"%.17g",value); vt_say_text(text); }
static inline void vt_say_bool(bool value) { vt_say_text(vt_bool_text(value)); }
static inline int64_t vt_length(const char *value,const char *where) { (void)where; return (int64_t)strlen(value); }
static inline const char *vt_arg(int64_t index,const char *where) {
    if(index<0 || index>=(int64_t)(vt_argc-1)) vt_fail(where,"Argument index is out of range.");
    const char *a=vt_argv[index+1];
    if(!vt_valid_utf8((const unsigned char *)a,strlen(a))) vt_fail(where,"Argument is not valid UTF-8.");
    return a;
}
static inline const char *vt_concat(const char *a,const char *b,const char *where) {
    size_t na=strlen(a),nb=strlen(b);
    if(na>SIZE_MAX/2 || nb>SIZE_MAX/2) vt_fail(where,"Text is too large.");
    char *text=vt_alloc(na+nb+1,where); memcpy(text,a,na); memcpy(text+na,b,nb+1); return text;
}

/* Text operations. Offsets are in bytes; slices must fall on UTF-8 character boundaries. */
static inline bool vt_boundary(const char *t,size_t i) { return ((unsigned char)t[i]&0xC0)!=0x80; }
static inline const char *vt_slice(const char *t,int64_t start,int64_t end,const char *where) {
    int64_t n=(int64_t)strlen(t);
    if(start<0 || end<start || end>n) vt_fail(where,"Slice is out of range.");
    if(!vt_boundary(t,(size_t)start) || !vt_boundary(t,(size_t)end)) vt_fail(where,"Slice would split a UTF-8 character.");
    return vt_text_copy(t+start,(size_t)(end-start),where);
}
static inline int64_t vt_find(const char *t,const char *needle,const char *where) { (void)where; const char *p=strstr(t,needle); return p?(int64_t)(p-t):-1; }
static inline const char *vt_trim(const char *t,const char *where) {
    size_t a=0,b=strlen(t);
    while(a<b && strchr(" \t\r\n\f\v",t[a])) a++;
    while(b>a && strchr(" \t\r\n\f\v",t[b-1])) b--;
    return vt_text_copy(t+a,b-a,where);
}
static inline bool vt_parse_int(const char *t,int64_t *out) {
    const char *p=t; bool negative=false; uint64_t value=0, limit;
    if(*p=='+' || *p=='-') negative=*p++=='-';
    if(!*p) return false;
    limit=negative?(uint64_t)INT64_MAX+1u:(uint64_t)INT64_MAX;
    for(;*p;p++) {
        if(*p<'0' || *p>'9') return false;
        unsigned d=(unsigned)(*p-'0');
        if(value>(limit-d)/10) return false;
        value=value*10+d;
    }
    *out=negative?(value==(uint64_t)INT64_MAX+1u?INT64_MIN:-(int64_t)value):(int64_t)value;
    return true;
}
static inline bool vt_parse_real(const char *t,double *out) {
    if(!*t || strchr(" \t\r\n\f\v",*t)) return false;
    for(const char *p=t;*p;p++) if(!strchr("0123456789+-.eE",*p)) return false;
    char *end; errno=0; double v=strtod(t,&end);
    if(*end || errno || !isfinite(v)) return false;
    *out=v; return true;
}
static inline int64_t vt_to_int(double v,const char *where) {
    if(!isfinite(v) || v>=9223372036854775808.0 || v<-9223372036854775808.0) vt_fail(where,"Real value does not fit in Int.");
    return (int64_t)v;
}

/* Lists. A list value is (length, shared buffer). Buffers only grow at the end, so a list never
 * sees items past its own length: appending to the newest list reuses the buffer; anything else
 * copies. This keeps lists immutable while push stays amortized O(1). */
typedef struct vt_buffer { int64_t used, cap; } vt_buffer;
typedef struct { int64_t len; vt_buffer *buf; } vt_list;
#define VT_HEADER ((sizeof(vt_buffer)+_Alignof(max_align_t)-1)/_Alignof(max_align_t)*_Alignof(max_align_t))
#define VT_ITEMS(T,list) ((T *)((char *)(list).buf+VT_HEADER))
static inline vt_list vt_list_grow(vt_list l,int64_t cap,size_t size,const char *where) {
    if(cap<0 || (uint64_t)cap>(SIZE_MAX-VT_HEADER)/size) vt_fail(where,"List is too large.");
    vt_buffer *b=vt_alloc(VT_HEADER+(size_t)cap*size,where);
    b->used=l.len; b->cap=cap;
    if(l.len) memcpy((char *)b+VT_HEADER,(char *)l.buf+VT_HEADER,(size_t)l.len*size);
    l.buf=b; return l;
}
static inline vt_list vt_list_push(vt_list l,const void *item,size_t size,const char *where) {
    if(!l.buf || l.len!=l.buf->used || l.buf->used==l.buf->cap) {
        if(l.len>INT64_MAX/2) vt_fail(where,"List is too large.");
        l=vt_list_grow(l,l.len<4?4:l.len*2,size,where);
    }
    memcpy((char *)l.buf+VT_HEADER+(size_t)l.len*size,item,size);
    l.buf->used=++l.len; return l;
}
static inline void vt_list_check(vt_list l,int64_t i,const char *where) { if(i<0 || i>=l.len) vt_fail(where,"List index is out of range."); }
static inline vt_list vt_list_set(vt_list l,int64_t i,const void *item,size_t size,const char *where) {
    vt_list_check(l,i,where);
    l=vt_list_grow(l,l.len,size,where);
    memcpy((char *)l.buf+VT_HEADER+(size_t)i*size,item,size); return l;
}
static inline vt_list vt_split(const char *t,const char *sep,const char *where) {
    vt_list l={0,NULL}; size_t n=strlen(sep);
    if(!n) vt_fail(where,"split needs a non-empty separator.");
    for(;;) {
        const char *p=strstr(t,sep);
        const char *piece=vt_text_copy(t,p?(size_t)(p-t):strlen(t),where);
        l=vt_list_push(l,&piece,sizeof piece,where);
        if(!p) return l;
        t=p+n;
    }
}
static inline const char *vt_join(vt_list l,const char *sep,const char *where) {
    size_t total=0,n=strlen(sep);
    for(int64_t i=0;i<l.len;i++) { total+=strlen(VT_ITEMS(const char *,l)[i])+(i?n:0); if(total>(size_t)VT_MAX_MEMORY) vt_fail(where,"Memory limit reached."); }
    char *out=vt_alloc(total+1,where),*p=out;
    for(int64_t i=0;i<l.len;i++) {
        if(i) { memcpy(p,sep,n); p+=n; }
        size_t k=strlen(VT_ITEMS(const char *,l)[i]); memcpy(p,VT_ITEMS(const char *,l)[i],k); p+=k;
    }
    *p=0; return out;
}

/* Input and files. Text is always NUL-free UTF-8; anything else is reported, not passed on. */
static inline const char *vt_error_text(const char *prefix,const char *where) {
    const char *reason=strerror(errno);
    return vt_concat(prefix,reason?reason:"unknown error",where);
}
static inline bool vt_read_line(const char **out,const char *where) {
    size_t cap=128,n=0; char *buf=malloc(cap); int c;
    if(!buf) vt_fail(where,"Unable to allocate memory.");
    fflush(stdout);
    while((c=getchar())!=EOF && c!='\n') {
        if(!c) { free(buf); vt_fail(where,"Input line contains a NUL character."); }
        if(n+1>=cap) { char *bigger=realloc(buf,cap*=2); if(!bigger) { free(buf); vt_fail(where,"Unable to allocate memory."); } buf=bigger; }
        buf[n++]=(char)c;
    }
    if(c==EOF && n==0) { free(buf); return false; }
    if(n && buf[n-1]=='\r') n--;
    if(!vt_valid_utf8((unsigned char *)buf,n)) { free(buf); vt_fail(where,"Input line is not valid UTF-8."); }
    *out=vt_text_copy(buf,n,where); free(buf); return true;
}
static inline const char *vt_read_file(const char *path,const char **error,const char *where) {
    FILE *f=fopen(path,"rb");
    if(!f) { *error=vt_error_text("Could not open file: ",where); return NULL; }
    size_t cap=4096,n=0; char *buf=malloc(cap);
    if(!buf) vt_fail(where,"Unable to allocate memory.");
    for(;;) {
        if(n==cap) { if(cap>(size_t)VT_MAX_MEMORY) { free(buf); fclose(f); vt_fail(where,"Memory limit reached."); } char *bigger=realloc(buf,cap*=2); if(!bigger) { free(buf); fclose(f); vt_fail(where,"Unable to allocate memory."); } buf=bigger; }
        size_t got=fread(buf+n,1,cap-n,f); n+=got;
        if(got==0) break;
    }
    bool failed=ferror(f); fclose(f);
    const char *result=NULL;
    if(failed) *error=vt_error_text("Could not read file: ",where);
    else if(memchr(buf,0,n)) *error="File contains a NUL byte; it is not text.";
    else if(!vt_valid_utf8((unsigned char *)buf,n)) *error="File is not valid UTF-8 text.";
    else result=vt_text_copy(buf,n,where);
    free(buf); return result;
}
static inline int64_t vt_write_file(const char *path,const char *text,const char **error,const char *where) {
    FILE *f=fopen(path,"wb");
    if(!f) { *error=vt_error_text("Could not open file for writing: ",where); return -1; }
    size_t n=strlen(text);
    bool ok=fwrite(text,1,n,f)==n;
    ok=(fclose(f)==0) && ok;
    if(!ok) { *error=vt_error_text("Could not write file: ",where); return -1; }
    return (int64_t)n;
}

/* Checked arithmetic. */
static inline int64_t vt_add(int64_t a,int64_t b,const char *w) {
    if((b>0 && a>INT64_MAX-b)||(b<0 && a<INT64_MIN-b)) vt_fail(w,"Int overflow in addition."); return a+b;
}
static inline int64_t vt_sub(int64_t a,int64_t b,const char *w) {
    if((b<0 && a>INT64_MAX+b)||(b>0 && a<INT64_MIN+b)) vt_fail(w,"Int overflow in subtraction."); return a-b;
}
static inline int64_t vt_neg(int64_t a,const char *w) { if(a==INT64_MIN) vt_fail(w,"Int overflow in negation."); return -a; }
static inline int64_t vt_mul(int64_t a,int64_t b,const char *w) {
    if(a>0 ? (b>0 ? a>INT64_MAX/b : b<INT64_MIN/a) : (a<0 ? (b>0 ? a<INT64_MIN/b : b<0 && a<INT64_MAX/b) : false)) vt_fail(w,"Int overflow in multiplication."); return a*b;
}
static inline int64_t vt_div(int64_t a,int64_t b,const char *w) {
    if(b==0) vt_fail(w,"Division by zero."); if(a==INT64_MIN && b==-1) vt_fail(w,"Int overflow in division.");
    int64_t q=a/b,r=a%b; if(r && ((r<0)!=(b<0))) --q; return q;
}
static inline int64_t vt_mod(int64_t a,int64_t b,const char *w) {
    if(b==0) vt_fail(w,"Division by zero."); if(a==INT64_MIN && b==-1) return 0;
    int64_t r=a%b; if(r && ((r<0)!=(b<0))) r+=b; return r;
}
static inline double vt_finite(double value,const char *w) { if(!isfinite(value)) vt_fail(w,"Real operation produced a non-finite result."); return value; }
static inline double vt_real_add(double a,double b,const char *w) { return vt_finite(a+b,w); }
static inline double vt_real_sub(double a,double b,const char *w) { return vt_finite(a-b,w); }
static inline double vt_real_mul(double a,double b,const char *w) { return vt_finite(a*b,w); }
static inline double vt_real_div(double a,double b,const char *w) { if(b==0.0) vt_fail(w,"Division by zero."); return vt_finite(a/b,w); }
#endif
