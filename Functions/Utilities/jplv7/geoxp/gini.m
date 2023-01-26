function [f,F,g,G,GINI]=gini(variable)
% PURPOSE: This function computes the Gini index and other related parameters for the Lorentz Curve
%------------------------------------------------------------------------
% USAGE: [f,F,f,G,GINI]=gini(variable)
%   where : variable = n x 1 vector of the variable to study
%------------------------------------------------------------------------
% OUTPUTS: f = (n x 1) vector of the frequencies of the sites whose value of variable is equal to Xk
%          F = (n x 1) vector of the frequencies of the sites whose value of variable is lower or equal to Xk
%          g = (n x 1) vector of the relative parts of the total weight of variable due to sites whose value is Xk
%          G = (n x 1) vector of the relative parts of the total weight of variable due to sites whose value is lower or equal to Xk
%          GINI = Gini index
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr



n=length(variable);
vsort=sort(variable);
N=histc(variable,vsort');
Xk=vsort(find(N~=0));
f=histc(variable,Xk');
f=f/n;
F=zeros(length(Xk),1);
for i=1:length(Xk)
    F(i)=length(find(variable<=Xk(i)));
end;
F=F/n;
g=(Xk.*f)/(sum(variable)/n);
G=cumsum(g);
F1=repmat(f,1,length(Xk));
F2=repmat(f',length(Xk),1);
X1=repmat(Xk,1,length(Xk));
X2=repmat(Xk',length(Xk),1);
T=(F1.*F2).*abs(X1-X2);
GINI=sum(T(:))/(2*sum(variable)/n);
 F=[0;F];
 G=[0;G];