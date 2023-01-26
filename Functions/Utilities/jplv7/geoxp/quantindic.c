#include "mex.h"
#include "matrix.h"

void quantindic(double Indic[], double var2[], double Xk[], int n, int lengXk)
{
    int i,j;
    for(j=0;j<n;j++)
    {
        for(i=0;i<lengXk;i++)
        {
            if(var2[j]<=Xk[i])
            {
                Indic[j*lengXk+i]=1;
            }
            else
            {
                Indic[j*lengXk+i]=0;
            }
        }
    }
}

void mexFunction (int nlhs, mxArray *plhs[], int nrhs, const mxArray *prhs[])
{
double *var2,*Xk,*Indic;
int n,lengXk;
var2=mxGetPr(prhs[0]);
Xk=mxGetPr(prhs[1]);
n=mxGetNumberOfElements(prhs[0]);
lengXk=mxGetNumberOfElements(prhs[1]);

//Indic=(double *) mxCalloc(lengXk*n,sizeof(double));
//quantindic(Indic,var2,Xk,n,lengXk);
plhs[0] = mxCreateDoubleMatrix(lengXk,n,mxREAL);
Indic=mxGetPr(plhs[0]);
quantindic(Indic,var2,Xk,n,lengXk);
//mxFree(mxGetPr(plhs[0]));
//mxSetPr(plhs[0], Indic);

}
