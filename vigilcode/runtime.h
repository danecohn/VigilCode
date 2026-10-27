/* SPDX-License-Identifier: GPL-3.0-or-later
 * VigilCode native support. No Python runtime or interpreter is linked. */
#ifndef VIGILCODE_RUNTIME_H
#define VIGILCODE_RUNTIME_H
#include <stdbool.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <limits.h>

static int vt_argc;
static char **vt_argv;
static uint64_t vt_steps=0, vt_output=0;
static size_t vt_memory=0;
typedef struct vt_allocation { struct vt_allocation *next; } vt_allocation;
static vt_allocation *vt_allocations=NULL;
static void vt_cleanup(void) { while(vt_allocations) { vt_allocation *next=vt_allocations->next; free(vt_allocations); vt_allocations=next; } }
static void vt_fail(const char *where, const char *message) {
    fprintf(stderr,"%s: VigilCode: %s\n",where,message); exit(1);
}
static void vt_obligation(const char *where, const char *kind, const char *message) {
    fprintf(stderr,"%s: %s not satisfied: %s\n",where,kind,message); exit(1);
}
/* Explicit v0.1 execution limits; resource policy can become configurable later. */
static void vt_step(const char *where) { if(++vt_steps>1000000) vt_fail(where,"Execution limit reached (1,000,000 work calls/loop steps)."); }
static void vt_write(const char *text) {
    size_t n=strlen(text);
    if(n>1048576 || vt_output>1048576-n) vt_fail("output","Output limit reached (1 MiB).");
    vt_output+=n; fputs(text,stdout);
}
static void vt_say_text(const char *value) { vt_write(value); vt_write("\n"); }
static void vt_say_int(int64_t value) { char text[64]; snprintf(text,sizeof text,"%" PRId64,value); vt_say_text(text); }
static void vt_say_real(double value) { char text[64]; snprintf(text,sizeof text,"%.17g",value); vt_say_text(text); }
static void vt_say_bool(bool value) { vt_say_text(value?"true":"false"); }
static int64_t vt_length(const char *value,const char *where) { (void)where; return (int64_t)strlen(value); }
static const char *vt_arg(int64_t index,const char *where) {
    if(index<0 || index>=(int64_t)(vt_argc-1)) vt_fail(where,"Argument index is out of range.");
    return vt_argv[index+1];
}
static const char *vt_concat(const char *a,const char *b,const char *where) {
    size_t na=strlen(a),nb=strlen(b),limit=16777216;
    if(na>limit || nb>limit || na+nb+1>limit || vt_memory>limit-(na+nb+1)) vt_fail(where,"Text allocation limit reached (16 MiB).");
    size_t n=na+nb+1;
    vt_allocation *block=malloc(sizeof(*block)+n);
    if(!block) vt_fail(where,"Unable to allocate text.");
    block->next=vt_allocations; vt_allocations=block; vt_memory+=n;
    char *text=(char *)(block+1); memcpy(text,a,na); memcpy(text+na,b,nb+1); return text;
}
static int64_t vt_add(int64_t a,int64_t b,const char *w) {
    if((b>0 && a>INT64_MAX-b)||(b<0 && a<INT64_MIN-b)) vt_fail(w,"Int overflow in addition."); return a+b;
}
static int64_t vt_sub(int64_t a,int64_t b,const char *w) {
    if((b<0 && a>INT64_MAX+b)||(b>0 && a<INT64_MIN+b)) vt_fail(w,"Int overflow in subtraction."); return a-b;
}
static int64_t vt_neg(int64_t a,const char *w) { if(a==INT64_MIN) vt_fail(w,"Int overflow in negation."); return -a; }
static int64_t vt_mul(int64_t a,int64_t b,const char *w) {
    if(a>0 ? (b>0 ? a>INT64_MAX/b : b<INT64_MIN/a) : (a<0 ? (b>0 ? a<INT64_MIN/b : b<0 && a<INT64_MAX/b) : false)) vt_fail(w,"Int overflow in multiplication."); return a*b;
}
static int64_t vt_div(int64_t a,int64_t b,const char *w) {
    if(b==0) vt_fail(w,"Division by zero."); if(a==INT64_MIN && b==-1) vt_fail(w,"Int overflow in division.");
    int64_t q=a/b,r=a%b; if(r && ((r<0)!=(b<0))) --q; return q;
}
static int64_t vt_mod(int64_t a,int64_t b,const char *w) {
    if(b==0) vt_fail(w,"Division by zero."); if(a==INT64_MIN && b==-1) return 0;
    int64_t r=a%b; if(r && ((r<0)!=(b<0))) r+=b; return r;
}
static double vt_finite(double value,const char *w) { if(!isfinite(value)) vt_fail(w,"Real operation produced a non-finite result."); return value; }
static double vt_real_add(double a,double b,const char *w) { return vt_finite(a+b,w); }
static double vt_real_sub(double a,double b,const char *w) { return vt_finite(a-b,w); }
static double vt_real_mul(double a,double b,const char *w) { return vt_finite(a*b,w); }
static double vt_real_div(double a,double b,const char *w) { if(b==0.0) vt_fail(w,"Division by zero."); return vt_finite(a/b,w); }
#endif
