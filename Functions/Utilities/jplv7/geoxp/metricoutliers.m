function [out]=metricoutliers(data,beta)
% PURPOSE : computes a data-based metric adapted to the detection of outliers
%---------------------------------------------------------------------------
% USAGE : [out]=metricoutliers(data,beta)
%    where : data = (n x p) data matrix
%            beta = strictly positive parameter (the default is beta=0.05)
%----------------------------------------------------------------------------- 
% OUTPUTS :  out = p x p matrix (metric)
%-----------------------------------------------------------------------------
%-----------------------------------------------------------------------------
% Anne Ruiz-Gazen, Julien Moutel, June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr


if nargin<2
    beta=0.05;
end;
x=data;
[n,p]=size(x);
xbar=sum(repmat(1/n*ones(n,1),1,p).*x)';
xc=x-ones(n,1)*xbar';
sig2=sum(repmat(1/n*ones(n,1),1,size(x,2)).*(x.^2))'-xbar.^2;
sigma=(size(x,1)/(size(x,1)-1))*diag(sig2);
sigmademi=sqrt(((size(x,1)-1)/size(x,1)))*diag(sig2.^(-1/2));
xc=xc*sigmademi;
cov=(xc'*xc)/n;
invcov=inv(cov);
normxc=diag(diag(xc*invcov*xc'));
weight=diag(diag(exp((-beta/2)*normxc)));
stdweight=weight/(diag(weight)'*ones(n,1));
outlier_cov=(stdweight*xc)'*xc;
out=inv(outlier_cov);