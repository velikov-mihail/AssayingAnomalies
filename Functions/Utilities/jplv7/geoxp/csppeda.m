function [as,bs,ppm]=csppeda(Z,c,half,m)
% CSPPEDA Projection pursuit exploratory data analysis.
%
%   [ALPHA,BETA,PPM] = CSPPEDA(Z,C,HALF,M)
%
%   This function implements projection pursuit exploratory
%   data analysis using the chi-square index. 
%
%   Z is an n x d matrix of observations that have been spered.
%   C is the size of the starting neighborhood for each search.
%   HALF is the number of steps without an increase in the index,
%   at which time the neighborhood is halved.
%   M is the number of random starts.
%
%   This uses the method of Posse. See the M-file for the references.
%
%   See also CSPPIND, CSPPSTRTREM

%   References: 
%   Christian Posse. 1995. 'Projection pursuit explortory
%   data analysis,' Computational Statistics and Data Analysis, vol. 29,
%   pp. 669-687.
%   Christian Posse. 1995. 'Tools for two-dimensional exploratory
%   projection pursuit,' J. of Computational and Graphical Statistics, vol 4
%   pp. 83-100

%   W. L. and A. R. Martinez, 9/15/01
%   Computational Statistics Toolbox 


% get the necessary constants
[n,p]=size(Z);
maxiter = 1500;
cs=c;
cstop = 0.00001;
cstop = 0.01;
as = zeros(p,1);	% storage for the information
bs = zeros(p,1);
ppm = realmin;


% find the probability of bivariate standard normal over
% each radial box.
fnr=inline('r.*exp(-0.5*r.^2)','r');
ck=ones(1,40);
ck(1:8)=quadl(fnr,0,sqrt(2*log(6))/5)/8;
ck(9:16)=quadl(fnr,sqrt(2*log(6))/5,2*sqrt(2*log(6))/5)/8;
ck(17:24)=quadl(fnr,2*sqrt(2*log(6))/5,3*sqrt(2*log(6))/5)/8;
ck(25:32)=quadl(fnr,3*sqrt(2*log(6))/5,4*sqrt(2*log(6))/5)/8;
ck(33:40)=quadl(fnr,4*sqrt(2*log(6))/5,5*sqrt(2*log(6))/5)/8;



for i=1:m  % m 
   % generate a random starting plane
   % this will be the current best plane
   a=randn(p,1);
   mag=sqrt(sum(a.^2));
   astar=a/mag;
   b=randn(p,1);
   bb=b-(astar'*b)*astar;
   mag=sqrt(sum(bb.^2));
   bstar=bb/mag;
   clear a mag b bb
   % find the projection index for this plane
   % this will be the initial value of the index
   ppimax = csppind(Z,astar,bstar,n,ck);
   
   % keep repeating this search until the value c becomes 
   % less than cstop or until the number of iterations exceeds maxiter
   mi=0;		% number of iterations
   h = 0;	% number of iterations without increase in index
   c=cs;
   while (mi < maxiter) & (c > cstop)	% Keep searching
      %disp(['Iter=' int2str(mi) '  c=' num2str(c) '  Index=' num2str(ppimax) '   i= ' int2str(i)])
      % generate a p-vector on the unit sphere
      v=randn(p,1);
      mag=sqrt(sum(v.^2));
      v1=v/mag;
      % find the a1,b1 and a2,b2 planes
      t=astar+c*v1;
      mag = sqrt(sum(t.^2));
      a1=t/mag;
      t=astar-c*v1;
      mag = sqrt(sum(t.^2));
      a2 = t/mag;
      t = bstar-(a1'*bstar)*a1;
      mag = sqrt(sum(t.^2));
      b1 = t/mag;
      t = bstar-(a2'*bstar)*a2;
      mag = sqrt(sum(t.^2));
      b2 = t/mag;
      ppi1 = csppind(Z,a1,b1,n,ck);
      ppi2 = csppind(Z,a2,b2,n,ck);
      [mp,ip]=max([ppi1,ppi2]);
      if mp > ppimax	% then reset plane and index to this value
         eval(['astar=a' int2str(ip) ';']);
         eval(['bstar=b' int2str(ip) ';']);
         eval(['ppimax=ppi' int2str(ip) ';']);
      else
         h = h+1;	% no increase 
      end
      mi=mi+1;
      if h==half	% then decrease the neighborhood
         c=c*.5;
         h=0;
      end
   end
   if ppimax > ppm
       % save the current projection as a best plane
       as = astar;
       bs = bstar;
       ppm = ppimax;
   end
end


   
   