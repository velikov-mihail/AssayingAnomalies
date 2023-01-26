function res=quant(var1,var2,pp,alpha)
% PURPOSE: This function computes conditional quantiles of the variable var2 given var1
%--------------------------------------------------------------
% USAGE: res = quant(var1,var2,p)
% where:   var1 =  first coordinates of the points of the sample (vector nx1)
%          var2 =  second coordinates of the points of the sample (vector nx1)
%          p = order of the quantile (scalar)
%          alpha = percentage used to compute the bandwidth
%--------------------------------------------------------------
% OUTPUTS: res =  (vector nx1)
%--------------------------------------------------------------
% NOTE: uses the kernel estimator given by the function fastbinsmooth.m
%--------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr

n=length(var1);
vsort=sort(var2);
N=histc(var2,vsort');
Xk=vsort(find(N~=0));
Fn=zeros(n,1);
evalXk=[min(Xk):(max(Xk)-min(Xk))/1000:max(Xk)]';
evalv1=[min(var1):(max(var1)-min(var1))/100:max(var1)]';
evalFn=zeros(length(evalv1),1);
[v1sort,ind1]=sort(var1);
N2=histc(var1,v1sort');
II=find(N2==0);
Fn(ind1)=[1:n];
if ~isempty(II)
    Fn(ind1(II))=Fn(ind1(II))+1;
end;
Fn=Fn/n;

h=alpha*(max(Fn)-min(Fn))/200;

for i=1:length(evalv1)
    evalFn(i)=length(find(var1<=evalv1(i)));
end;
evalFn=evalFn/n;



Fechap=sparse(length(evalXk),length(evalFn));
p=floor(5000000/n);

niter=floor(length(evalXk)/p);


for i=1:niter
    Xkt=evalXk(1+(i-1)*p:p+(i-1)*p);
    Indic2=quantindic(var2,Xkt);
    for j=1+(i-1)*p:p+(i-1)*p
        Fchap(j,:)=fastbinsmooth([Fn';Indic2(j-(i-1)*p,:)],h,[min(evalFn),max(evalFn)],101,2,3,0,1)';
    end;
end;
if (niter*p)<length(evalXk)
    Xkt=evalXk(niter*p+1:length(evalXk));
    Indic2=quantindic(var2,Xkt);
    for j=niter*p+1:length(evalXk)
       Fchap(j,:)=fastbinsmooth([Fn';Indic2(j-niter*p,:)],h,[min(evalFn),max(evalFn)],101,2,3,0,1)';
    end; 
end;
        


res=zeros(length(evalv1),1);
for j=1:length(evalv1)
    res(j)=invgen([evalXk,Fchap(:,j)],pp);
end;

